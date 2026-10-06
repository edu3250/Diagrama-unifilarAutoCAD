"""Client for the B2 AutoCAD plug-in's named-pipe bridge (ADR-0001, spike S2).

The plug-in writes ``%LOCALAPPDATA%\\pvsld\\bridge\\autocad-<pid>.json`` (current-user ACL) with
the pipe name and a secret generated at each AutoCAD start. :func:`discover_endpoint` reads it,
and :class:`PipeClient` authenticates with the secret and then sends newline-delimited JSON-RPC.

Every call has a deadline. A timeout or a lost connection closes the stream (a late reply can
never be matched to the next request); the next call reconnects and authenticates again.
"""

from __future__ import annotations

import itertools
import json
import os
import sys
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pvsld.transports.protocol import (
    MAX_LINE_BYTES,
    PROTOCOL_VERSION,
    BridgeAuthError,
    BridgeConnectionError,
    BridgeProtocolError,
    BridgeTimeoutError,
    LineBuffer,
    decode,
    encode,
    error_from_payload,
    request,
)
from pvsld.transports.streams import READ_CHUNK, ByteStream

DISCOVERY_DIR_ENV = "PVSLD_BRIDGE_DIR"

StreamOpener = Callable[[float], ByteStream]
"""Opens a fresh connection within the given number of seconds."""


def default_discovery_dir() -> Path:
    """``$PVSLD_BRIDGE_DIR``, else ``%LOCALAPPDATA%\\pvsld\\bridge`` (where the plug-in writes)."""
    override = os.environ.get(DISCOVERY_DIR_ENV)
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "pvsld" / "bridge"


@dataclass(frozen=True)
class BridgeEndpoint:
    """Where a running bridge listens, and the secret it expects."""

    pipe: str
    secret: str = field(repr=False)
    pid: int
    protocol: int = PROTOCOL_VERSION
    server: str = ""
    host_version: str = ""
    path: Path | None = None

    @classmethod
    def from_file(cls, path: Path) -> BridgeEndpoint:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise BridgeConnectionError(f"unreadable bridge discovery file {path}: {exc}") from exc
        if not isinstance(data, dict):
            raise BridgeConnectionError(f"bridge discovery file {path} is not a JSON object")
        try:
            endpoint = cls(
                pipe=str(data["pipe"]),
                secret=str(data["secret"]),
                pid=int(data["pid"]),
                protocol=int(data.get("protocol", 0)),
                server=str(data.get("server", "")),
                host_version=str(data.get("host_version", "")),
                path=path,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise BridgeConnectionError(f"bridge discovery file {path} lacks {exc}") from exc
        if endpoint.protocol != PROTOCOL_VERSION:
            raise BridgeConnectionError(
                f"{path} announces bridge protocol {endpoint.protocol}; this client speaks "
                f"{PROTOCOL_VERSION}. Update the plug-in or pvsld so they match."
            )
        return endpoint


def pid_alive(pid: int) -> bool:
    """Whether a process with this id is running."""
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
        if not handle:
            return False
        try:
            code = ctypes.c_ulong()
            return bool(kernel32.GetExitCodeProcess(handle, ctypes.byref(code))) and (
                code.value == 259  # STILL_ACTIVE
            )
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def discover_endpoint(
    directory: Path | None = None,
    *,
    pid: int | None = None,
    is_alive: Callable[[int], bool] = pid_alive,
) -> BridgeEndpoint:
    """Find a live bridge: the one for ``pid`` if given, else the most recently started one.

    Files left behind by AutoCAD processes that no longer exist are ignored.
    """
    directory = directory or default_discovery_dir()
    pattern = f"autocad-{pid}.json" if pid is not None else "autocad-*.json"
    candidates = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    stale = []
    for path in candidates:
        endpoint = BridgeEndpoint.from_file(path)
        if is_alive(endpoint.pid):
            return endpoint
        stale.append(path.name)
    hint = f" (stale files from exited AutoCAD processes: {', '.join(stale)})" if stale else ""
    target = f"for AutoCAD pid {pid}" if pid is not None else ""
    raise BridgeConnectionError(
        f"no running pvsld bridge {target} in {directory}{hint}. Start AutoCAD and NETLOAD "
        "PvSld.AutoCAD.dll (docs/spikes/s2-autocad-connectivity.md)."
    )


class PipeClient:
    """Synchronous JSON-RPC client for the bridge. Not thread-safe: use one per thread."""

    def __init__(
        self,
        open_stream: StreamOpener,
        secret: str,
        *,
        timeout: float = 30.0,
        connect_timeout: float = 5.0,
        max_line_bytes: int = MAX_LINE_BYTES,
    ) -> None:
        self._open_stream = open_stream
        self._secret = secret
        self.timeout = timeout
        self.connect_timeout = connect_timeout
        self._max_line_bytes = max_line_bytes
        self._ids = itertools.count(1)
        self._stream: ByteStream | None = None
        self._buffer = LineBuffer(max_line_bytes)
        self._ready: list[bytes] = []
        self.server_info: dict[str, Any] = {}

    @classmethod
    def for_endpoint(cls, endpoint: BridgeEndpoint, **kwargs: Any) -> PipeClient:
        """A client for a real Windows named pipe, checking that AutoCAD itself serves it."""
        if sys.platform != "win32":
            raise BridgeConnectionError("the AutoCAD bridge pipe exists only on Windows")
        from pvsld.transports.streams import WindowsPipeStream

        def open_stream(timeout: float) -> ByteStream:
            return WindowsPipeStream.connect(
                endpoint.pipe, timeout, expected_server_pid=endpoint.pid
            )

        return cls(open_stream, endpoint.secret, **kwargs)

    # -- connection ---------------------------------------------------------------------------

    @property
    def connected(self) -> bool:
        return self._stream is not None

    def connect(self) -> dict[str, Any]:
        """Open the stream and authenticate; returns the server's hello."""
        self.close()
        self._stream = self._open_stream(self.connect_timeout)
        self._buffer = LineBuffer(self._max_line_bytes)
        self._ready = []
        self.server_info = self._exchange("auth", {"secret": self._secret}, self.connect_timeout)
        return self.server_info

    def close(self) -> None:
        stream, self._stream = self._stream, None
        if stream is not None:
            stream.close()

    def __enter__(self) -> PipeClient:
        self.connect()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- calls --------------------------------------------------------------------------------

    def call(
        self, method: str, params: Mapping[str, Any] | None = None, *, timeout: float | None = None
    ) -> Any:
        """Send one request and return its ``result``; raises a ``Bridge*Error`` otherwise."""
        if self._stream is None:
            self.connect()
        return self._exchange(
            method, dict(params) if params is not None else None, timeout or self.timeout
        )

    def _exchange(self, method: str, params: dict[str, Any] | None, timeout: float) -> Any:
        deadline = time.monotonic() + timeout
        request_id = next(self._ids)
        try:
            self._send(encode(request(request_id, method, params)), deadline)
            while True:
                message = self._receive(deadline)
                if "error" in message and message.get("id") in (request_id, None):
                    raise error_from_payload(message["error"])
                if message.get("id") != request_id:
                    continue  # not ours (cannot happen on a fresh stream; kept defensive)
                if "result" not in message:
                    raise BridgeProtocolError(f"response without result or error: {message!r}")
                return message["result"]
        except (BridgeTimeoutError, BridgeConnectionError, BridgeProtocolError, BridgeAuthError):
            self.close()  # the stream is unusable (or the server already closed it)
            raise

    def _send(self, data: bytes, deadline: float) -> None:
        assert self._stream is not None
        try:
            self._stream.send(data, max(0.0, deadline - time.monotonic()))
        except TimeoutError as exc:
            raise BridgeTimeoutError("timed out sending to the AutoCAD bridge") from exc

    def _receive(self, deadline: float) -> dict[str, Any]:
        assert self._stream is not None
        while not self._ready:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise BridgeTimeoutError("the AutoCAD bridge did not answer in time")
            try:
                chunk = self._stream.recv(READ_CHUNK, remaining)
            except TimeoutError as exc:
                raise BridgeTimeoutError("the AutoCAD bridge did not answer in time") from exc
            if not chunk:
                raise BridgeConnectionError("the AutoCAD bridge closed the connection")
            self._ready.extend(line for line in self._buffer.feed(chunk) if line)
        return decode(self._ready.pop(0))

    # -- typed helpers for the allowlisted methods --------------------------------------------

    def ping(self, *, main_thread: bool = False, timeout: float | None = None) -> dict[str, Any]:
        """Transport round trip; with ``main_thread`` also a hop through AutoCAD's main thread."""
        return self.call("ping", {"main_thread": main_thread}, timeout=timeout)

    def insert_block(
        self,
        block: str,
        position: Sequence[float],
        attributes: Mapping[str, str] | None = None,
        *,
        document: str | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "block": block,
            "position": list(position),
            "attributes": dict(attributes or {}),
        }
        if document is not None:
            params["document"] = document
        return self.call("insert_block", params, timeout=timeout)

    def read_attributes(
        self,
        *,
        handle: str | None = None,
        block: str | None = None,
        document: str | None = None,
        timeout: float | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {}
        if handle is not None:
            params["handle"] = handle
        if block is not None:
            params["block"] = block
        if document is not None:
            params["document"] = document
        return self.call("read_attributes", params, timeout=timeout)["references"]

    def batch(
        self,
        block: str,
        inserts: Iterable[Mapping[str, Any]],
        lines: Iterable[Mapping[str, Any]] = (),
        *,
        document: str | None = None,
        inject_failure_after: int | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """Create attributed inserts and lines in one AutoCAD transaction (all or nothing).

        ``inserts`` items are ``{"position": [x, y], "attributes": {...}}``; ``lines`` items are
        ``{"start": [x, y], "end": [x, y]}``. ``inject_failure_after`` is a test hook that makes
        the plug-in fail after that many entities, before commit.
        """
        params: dict[str, Any] = {
            "block": block,
            "inserts": [dict(item) for item in inserts],
            "lines": [dict(item) for item in lines],
        }
        if document is not None:
            params["document"] = document
        if inject_failure_after is not None:
            params["inject_failure_after"] = inject_failure_after
        return self.call("batch", params, timeout=timeout)

    def drawing_stats(
        self, *, document: str | None = None, timeout: float | None = None
    ) -> dict[str, Any]:
        params = {"document": document} if document is not None else {}
        return self.call("drawing_stats", params, timeout=timeout)
