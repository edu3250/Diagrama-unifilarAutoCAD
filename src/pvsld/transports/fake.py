"""An in-process fake of the B2 AutoCAD plug-in that speaks the real bridge protocol.

It mirrors ``plugin/src/PvSld.AutoCAD`` closely enough to test the client (and, later, MCP tools)
without AutoCAD: secret handshake, the allowlisted methods, all-or-nothing batches with the
``inject_failure_after`` hook, and busy errors on demand. It listens on TCP (any OS) or, on
Windows, on a named pipe. It is a test double, not a security boundary.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import math
import os
import re
import secrets
import socket
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any

from pvsld.transports.protocol import (
    MAX_LINE_BYTES,
    METHODS,
    PROTOCOL_VERSION,
    BridgeConnectionError,
    BridgeProtocolError,
    ErrorCode,
    LineBuffer,
    decode,
    encode,
    error_response,
    result_response,
)
from pvsld.transports.streams import READ_CHUNK, ByteStream, SocketStream

TEST_SYMBOL_TAGS = ("COMP_ID", "LABEL", "RATING")
MAX_BATCH_ITEMS = 5000
_BLOCK_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class RpcError(Exception):
    """A JSON-RPC error the fake reports to its client."""

    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass
class FakeEntity:
    handle: str
    kind: str  # "insert" or "line"
    block: str | None = None
    position: tuple[float, float, float] = (0.0, 0.0, 0.0)
    end: tuple[float, float, float] | None = None
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class FakeDrawing:
    name: str
    entities: dict[str, FakeEntity] = field(default_factory=dict)
    blocks: dict[str, tuple[str, ...]] = field(default_factory=dict)
    next_handle: int = 0x200

    def new_handle(self) -> str:
        self.next_handle += 1
        return format(self.next_handle, "X")

    def snapshot(self) -> dict[str, Any]:
        handles = sorted(self.entities)
        return {
            "modelspace_entities": len(handles),
            "block_definitions": sorted(self.blocks),
            "modelspace_digest": hashlib.sha256(",".join(handles).encode("ascii")).hexdigest(),
        }


class FakeBridgeServer:
    """See the module docstring; ``busy``, ``delay`` and ``close_after`` inject faults."""

    def __init__(
        self,
        secret: str | None = None,
        *,
        documents: tuple[str, ...] = ("Drawing1.dwg",),
        auth_timeout: float = 5.0,
        max_line_bytes: int = MAX_LINE_BYTES,
    ) -> None:
        self.secret = secret or secrets.token_urlsafe(32)
        self.drawings = {name: FakeDrawing(name) for name in documents}
        self.active_document = documents[0] if documents else None
        self.auth_timeout = auth_timeout
        self.max_line_bytes = max_line_bytes
        #: ``(reason, message)``: every drawing request answers "busy" while set.
        self.busy: tuple[str, str] | None = None
        #: Seconds to wait before answering each authenticated request.
        self.delay = 0.0
        #: Close the connection after this many answered requests (simulates a crash).
        self.close_after: int | None = None
        self.methods_seen: list[str] = []
        self.auth_failures = 0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    # -- listeners ----------------------------------------------------------------------------

    def listen_tcp(self, host: str = "127.0.0.1") -> tuple[str, int]:
        """Serve on a free localhost TCP port; returns ``(host, port)``."""
        server = socket.create_server((host, 0))
        server.settimeout(0.1)
        address = server.getsockname()[:2]

        def accept_loop() -> None:
            with server:
                while not self._stop.is_set():
                    try:
                        conn, _ = server.accept()
                    except TimeoutError:
                        continue
                    except OSError:
                        break
                    self._spawn(self.serve, SocketStream(conn))

        self._spawn(accept_loop)
        return address

    def listen_pipe(self, name: str) -> None:
        """Serve on ``\\\\.\\pipe\\<name>`` (Windows only)."""
        if sys.platform != "win32":
            raise OSError("named pipes need Windows")
        import pywintypes
        import win32event
        import win32file
        import win32pipe
        import winerror

        from pvsld.transports.streams import WindowsPipeStream

        path = rf"\\.\pipe\{name}"

        def create() -> Any:
            return win32pipe.CreateNamedPipe(
                path,
                win32pipe.PIPE_ACCESS_DUPLEX | win32file.FILE_FLAG_OVERLAPPED,
                win32pipe.PIPE_TYPE_BYTE | win32pipe.PIPE_READMODE_BYTE | win32pipe.PIPE_WAIT,
                win32pipe.PIPE_UNLIMITED_INSTANCES,
                65536,
                65536,
                0,
                None,
            )

        first = create()

        def accept_loop() -> None:
            handle = first
            event = win32event.CreateEvent(None, True, False, None)
            try:
                while not self._stop.is_set():
                    overlapped = pywintypes.OVERLAPPED()
                    overlapped.hEvent = event
                    win32event.ResetEvent(event)
                    try:
                        win32pipe.ConnectNamedPipe(handle, overlapped)
                    except pywintypes.error as exc:
                        if exc.winerror != winerror.ERROR_PIPE_CONNECTED:
                            raise
                        win32event.SetEvent(event)
                    while not self._stop.is_set():
                        if win32event.WaitForSingleObject(event, 100) == win32event.WAIT_OBJECT_0:
                            break
                    if self._stop.is_set():
                        break
                    connected, handle = handle, create()
                    self._spawn(self.serve, WindowsPipeStream(connected))
            finally:
                win32file.CloseHandle(handle)
                win32file.CloseHandle(event)

        self._spawn(accept_loop)

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=5)

    def __enter__(self) -> FakeBridgeServer:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.stop()

    def _spawn(self, target: Any, *args: Any) -> None:
        thread = threading.Thread(target=target, args=args, daemon=True)
        self._threads.append(thread)
        thread.start()

    # -- conversation -------------------------------------------------------------------------

    def serve(self, stream: ByteStream) -> None:
        """Run one connection until the client leaves, auth fails or the server stops."""
        buffer = LineBuffer(self.max_line_bytes)
        pending: list[bytes] = []
        authenticated = False
        answered = 0
        auth_deadline = time.monotonic() + self.auth_timeout
        try:
            while not self._stop.is_set():
                if not pending:
                    wait = 0.1 if authenticated else auth_deadline - time.monotonic()
                    if wait <= 0:
                        self._refuse(stream, None, "authentication timed out")
                        return
                    try:
                        chunk = stream.recv(READ_CHUNK, min(wait, 0.1))
                    except TimeoutError:
                        continue
                    if not chunk:
                        return
                    try:
                        pending.extend(buffer.feed(chunk))
                    except BridgeProtocolError as exc:
                        self._send(
                            stream, error_response(None, ErrorCode.INVALID_REQUEST, str(exc))
                        )
                        return
                    continue

                line = pending.pop(0)
                if not line:
                    continue
                try:
                    request_id, method, params = _parse_request(line)
                except RpcError as exc:
                    self._send(stream, error_response(_guess_id(line), exc.code, exc.message))
                    if not authenticated:
                        self._count_auth_failure()
                        return
                    continue

                if not authenticated or method == "auth":
                    if method != "auth" or not self._secret_ok(params):
                        self._refuse(
                            stream,
                            request_id,
                            'unauthorized: the first request must be "auth" with the secret '
                            "from the bridge discovery file",
                        )
                        return
                    authenticated = True
                    self._send(stream, result_response(request_id, self._hello()))
                    continue

                if self.delay:
                    time.sleep(self.delay)
                with self._lock:
                    self.methods_seen.append(method)
                    try:
                        response = result_response(request_id, self.handle(method, params))
                    except RpcError as exc:
                        response = error_response(request_id, exc.code, exc.message, exc.data)
                self._send(stream, response)
                answered += 1
                if self.close_after is not None and answered >= self.close_after:
                    return
        except (BridgeConnectionError, OSError):
            return  # the client went away
        finally:
            stream.close()

    def _refuse(self, stream: ByteStream, request_id: Any, message: str) -> None:
        self._count_auth_failure()
        self._send(stream, error_response(request_id, ErrorCode.UNAUTHORIZED, message))

    def _count_auth_failure(self) -> None:
        with self._lock:
            self.auth_failures += 1

    @staticmethod
    def _send(stream: ByteStream, message: dict) -> None:
        stream.send(encode(message), 5.0)

    def _secret_ok(self, params: dict[str, Any] | None) -> bool:
        secret = (params or {}).get("secret")
        return isinstance(secret, str) and hmac.compare_digest(
            secret.encode("utf-8"), self.secret.encode("utf-8")
        )

    @staticmethod
    def _hello() -> dict[str, Any]:
        return {
            "server": "pvsld-fake-bridge",
            "version": "0.2.0",
            "protocol": PROTOCOL_VERSION,
            "methods": list(METHODS),
        }

    # -- methods (caller holds the lock) ------------------------------------------------------

    def handle(self, method: str, params: dict[str, Any] | None) -> Any:
        handlers = {
            "ping": self._ping,
            "insert_block": self._insert_block,
            "read_attributes": self._read_attributes,
            "batch": self._batch,
            "drawing_stats": self._drawing_stats,
        }
        if method not in handlers:
            raise RpcError(
                ErrorCode.METHOD_NOT_FOUND,
                f"unknown method '{method}'; the bridge accepts only: {', '.join(METHODS)}",
            )
        return handlers[method](params or {})

    def _ping(self, params: dict[str, Any]) -> dict[str, Any]:
        main_thread = _bool(params, "main_thread")
        if main_thread and self.busy and self.busy[0] == "main_thread_unavailable":
            self._raise_busy()
        result: dict[str, Any] = {
            "pong": True,
            "pid": os.getpid(),
            "host_version": "fake",
            "server_version": "0.2.0",
            "main_thread": main_thread,
        }
        if main_thread:
            result["documents"] = len(self.drawings)
        return result

    def _insert_block(self, params: dict[str, Any]) -> dict[str, Any]:
        block = _block_name(params)
        position = _point(params.get("position"), "position")
        attributes = _string_map(params.get("attributes"), "attributes")

        def body(drawing: FakeDrawing) -> dict[str, Any]:
            created = _ensure_block(drawing, block)
            _validate_tags(drawing, block, attributes)
            entity = _insert(drawing, block, position, attributes)
            return {
                "handle": entity.handle,
                "attributes": dict(entity.attributes),
                "created_block_definition": created,
            }

        return self._transaction(params, body)

    def _read_attributes(self, params: dict[str, Any]) -> dict[str, Any]:
        handle = _string(params, "handle", max_length=16)
        block = _block_name(params) if params.get("block") is not None else None
        if (handle is None) == (block is None):
            raise RpcError(ErrorCode.INVALID_PARAMS, 'give exactly one of "handle" or "block"')

        def body(drawing: FakeDrawing) -> dict[str, Any]:
            if handle is not None:
                entity = drawing.entities.get(handle.upper())
                if entity is None:
                    raise RpcError(
                        ErrorCode.INVALID_PARAMS, f"no entity with handle {handle} in this drawing"
                    )
                if entity.kind != "insert":
                    raise RpcError(
                        ErrorCode.INVALID_PARAMS, f"handle {handle} is not a block reference"
                    )
                found = [entity]
            else:
                found = sorted(
                    (e for e in drawing.entities.values() if e.block == block),
                    key=lambda e: e.handle,
                )
            return {
                "references": [
                    {
                        "handle": e.handle,
                        "block": e.block,
                        "position": list(e.position),
                        "attributes": dict(e.attributes),
                    }
                    for e in found
                ]
            }

        return self._transaction(params, body, write=False)

    def _batch(self, params: dict[str, Any]) -> dict[str, Any]:
        block = _block_name(params)
        inserts = [
            (
                _point(_object(item, "inserts[]").get("position"), "inserts[].position"),
                _string_map(item.get("attributes"), "inserts[].attributes"),
            )
            for item in _array(params, "inserts")
        ]
        lines = [
            (
                _point(_object(item, "lines[]").get("start"), "lines[].start"),
                _point(item.get("end"), "lines[].end"),
            )
            for item in _array(params, "lines")
        ]
        if len(inserts) + len(lines) > MAX_BATCH_ITEMS:
            raise RpcError(
                ErrorCode.INVALID_PARAMS,
                f"a batch may hold at most {MAX_BATCH_ITEMS} inserts and lines in total",
            )
        fail_after = _int(params, "inject_failure_after", 0, MAX_BATCH_ITEMS)
        started = time.perf_counter()

        def body(drawing: FakeDrawing) -> dict[str, Any]:
            created = _ensure_block(drawing, block)
            for _, attributes in inserts:
                _validate_tags(drawing, block, attributes)
            appended = 0
            handles = []
            for position, attributes in inserts:
                _maybe_fail(fail_after, appended)
                handles.append(_insert(drawing, block, position, attributes).handle)
                appended += 1
            for start, end in lines:
                _maybe_fail(fail_after, appended)
                handle = drawing.new_handle()
                drawing.entities[handle] = FakeEntity(handle, "line", position=start, end=end)
                appended += 1
            _maybe_fail(fail_after, appended)
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            return {
                "inserted": len(inserts),
                "lines": len(lines),
                "handles": handles,
                "created_block_definition": created,
                "main_thread_ms": elapsed,
                "server_ms": elapsed,
            }

        return self._transaction(params, body)

    def _drawing_stats(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._transaction(params, lambda drawing: drawing.snapshot(), write=False)

    def _transaction(self, params: dict[str, Any], body: Any, *, write: bool = True) -> Any:
        """Resolve the drawing, refuse if busy, run ``body`` on a copy and commit on success."""
        name = _string(params, "document")
        drawing = self._resolve(name)
        if self.busy:
            self._raise_busy()
        working = copy.deepcopy(drawing) if write else drawing
        try:
            result = body(working)
        except RpcError:
            raise
        except _InjectedFailureError as exc:
            raise RpcError(
                ErrorCode.OPERATION_FAILED,
                f"injected failure after {exc.args[0]} entities (test hook). The transaction "
                "was rolled back; the drawing is unchanged.",
                {"rolled_back": True, "injected": True},
            ) from exc
        if write:
            self.drawings[drawing.name] = working
        return result

    def _resolve(self, name: str | None) -> FakeDrawing:
        if name is None:
            if self.active_document is None:
                raise RpcError(
                    ErrorCode.DOCUMENT_NOT_FOUND,
                    "No drawing is open in AutoCAD. Open or create a drawing and retry.",
                )
            return self.drawings[self.active_document]
        for drawing in self.drawings.values():
            if drawing.name.lower() == name.lower():
                return drawing
        raise RpcError(
            ErrorCode.DOCUMENT_NOT_FOUND,
            f"No open drawing is named '{name}'. Open drawings: {', '.join(self.drawings)}.",
        )

    def _raise_busy(self) -> None:
        assert self.busy is not None
        reason, message = self.busy
        raise RpcError(ErrorCode.BUSY, message, {"reason": reason, "retry_after_ms": 1000})


class _InjectedFailureError(Exception):
    """Raised by the ``inject_failure_after`` test hook."""


def _maybe_fail(fail_after: int | None, appended: int) -> None:
    if fail_after == appended:
        raise _InjectedFailureError(appended)


def _ensure_block(drawing: FakeDrawing, block: str) -> bool:
    if block in drawing.blocks:
        return False
    drawing.blocks[block] = TEST_SYMBOL_TAGS
    return True


def _validate_tags(drawing: FakeDrawing, block: str, attributes: dict[str, str]) -> None:
    tags = drawing.blocks[block]
    unknown = [key for key in attributes if key.upper() not in tags]
    if unknown:
        raise RpcError(
            ErrorCode.INVALID_PARAMS,
            f"block '{block}' has no attribute(s) {', '.join(unknown)}; "
            f"its tags are {', '.join(tags)}",
        )


def _insert(
    drawing: FakeDrawing, block: str, position: tuple[float, float, float], values: dict[str, str]
) -> FakeEntity:
    upper = {key.upper(): value for key, value in values.items()}
    handle = drawing.new_handle()
    entity = FakeEntity(
        handle,
        "insert",
        block=block,
        position=position,
        attributes={tag: upper.get(tag, "") for tag in drawing.blocks[block]},
    )
    drawing.entities[handle] = entity
    return entity


def _parse_request(line: bytes) -> tuple[Any, str, dict[str, Any] | None]:
    try:
        message = decode(line)
    except BridgeProtocolError as exc:
        raise RpcError(ErrorCode.PARSE_ERROR, str(exc)) from exc
    if message.get("jsonrpc") != "2.0":
        raise RpcError(ErrorCode.INVALID_REQUEST, '"jsonrpc" must be "2.0"')
    request_id = message.get("id")
    if isinstance(request_id, bool) or not isinstance(request_id, (int, float, str)):
        raise RpcError(
            ErrorCode.INVALID_REQUEST,
            '"id" must be a string or a number (notifications are not supported)',
        )
    if not isinstance(message.get("method"), str):
        raise RpcError(ErrorCode.INVALID_REQUEST, '"method" must be a string')
    params = message.get("params")
    if params is not None and not isinstance(params, dict):
        raise RpcError(
            ErrorCode.INVALID_REQUEST, '"params" must be an object (by-name parameters only)'
        )
    return request_id, message["method"], params


def _guess_id(line: bytes) -> Any:
    try:
        request_id = decode(line).get("id")
    except BridgeProtocolError:
        return None
    return request_id if isinstance(request_id, (int, str)) else None


def _invalid(message: str) -> RpcError:
    return RpcError(ErrorCode.INVALID_PARAMS, message)


def _string(params: dict[str, Any], name: str, *, max_length: int = 256) -> str | None:
    value = params.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _invalid(f'parameter "{name}" must be a string')
    if len(value) > max_length:
        raise _invalid(f'parameter "{name}" is longer than {max_length} characters')
    return value


def _bool(params: dict[str, Any], name: str) -> bool:
    value = params.get(name, False)
    if not isinstance(value, bool):
        raise _invalid(f'parameter "{name}" must be true or false')
    return value


def _int(params: dict[str, Any], name: str, low: int, high: int) -> int | None:
    value = params.get(name)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise _invalid(f'parameter "{name}" must be an integer')
    if not low <= value <= high:
        raise _invalid(f'parameter "{name}" must be between {low} and {high}')
    return value


def _block_name(params: dict[str, Any]) -> str:
    name = _string(params, "block", max_length=64)
    if name is None:
        raise _invalid('missing string parameter "block"')
    if not _BLOCK_NAME.match(name):
        raise _invalid("\"block\" may contain only letters, digits, '_' and '-' (1-64 characters)")
    return name


def _point(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or not 2 <= len(value) <= 3:
        raise _invalid(f'"{name}" must be an array [x, y] or [x, y, z]')
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
        for v in value
    ):
        raise _invalid(f'"{name}" must contain finite numbers')
    x, y, *rest = (float(v) for v in value)
    return (x, y, rest[0] if rest else 0.0)


def _string_map(value: Any, name: str) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise _invalid(f'"{name}" must be an object of strings')
    for key, text in value.items():
        if not isinstance(text, str):
            raise _invalid(f'"{name}.{key}" must be a string')
        if len(text) > 256:
            raise _invalid(f'"{name}.{key}" is longer than 256 characters')
    return dict(value)


def _array(params: dict[str, Any], name: str) -> list[Any]:
    value = params.get(name)
    if value is None:
        return []
    if not isinstance(value, list):
        raise _invalid(f'parameter "{name}" must be an array')
    if len(value) > MAX_BATCH_ITEMS:
        raise _invalid(f'parameter "{name}" has more than {MAX_BATCH_ITEMS} items')
    return value


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(f"each {name} item must be an object")
    return value
