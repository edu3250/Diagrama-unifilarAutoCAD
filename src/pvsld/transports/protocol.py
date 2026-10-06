"""Wire protocol of the B2 AutoCAD bridge (ADR-0001, spike S2).

One JSON-RPC 2.0 object per line (UTF-8, ``\\n``-terminated), the framing MCP uses on stdio. The
first request on every connection must be ``auth`` with the per-start secret from the discovery
file; anything else closes the connection. The C# side lives in
``plugin/src/PvSld.Bridge/BridgeProtocol.cs``; keep both in step.
"""

from __future__ import annotations

import json
from enum import IntEnum
from typing import Any

PROTOCOL_VERSION = 1
MAX_LINE_BYTES = 8 * 1024 * 1024

#: The bridge's allowlist. It executes nothing else: no LISP, no command strings, no code.
METHODS = ("auth", "ping", "insert_block", "read_attributes", "batch", "drawing_stats")


class ErrorCode(IntEnum):
    """JSON-RPC error codes; -32001..-32005 are bridge-specific server errors."""

    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603
    UNAUTHORIZED = -32001
    BUSY = -32002
    OPERATION_FAILED = -32003
    TIMEOUT = -32004
    DOCUMENT_NOT_FOUND = -32005


class BusyReason:
    """Values of ``error.data.reason`` for :attr:`ErrorCode.BUSY`."""

    MODAL_DIALOG = "modal_dialog"
    COMMAND_ACTIVE = "command_active"
    NOT_QUIESCENT = "not_quiescent"
    DOCUMENT_LOCKED = "document_locked"
    MAIN_THREAD_UNAVAILABLE = "main_thread_unavailable"
    BRIDGE_BUSY = "bridge_busy"


class BridgeError(Exception):
    """Base class of every bridge client error."""


class BridgeConnectionError(BridgeError):
    """The bridge cannot be reached, or the connection was lost."""


class BridgeTimeoutError(BridgeError):
    """No response arrived in time; the connection is dropped so a late reply cannot be misread."""


class BridgeProtocolError(BridgeError):
    """The peer sent something that is not a valid bridge message."""


class BridgeRemoteError(BridgeError):
    """The bridge answered with a JSON-RPC error."""

    def __init__(self, code: int, message: str, data: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data or {}

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


class BridgeAuthError(BridgeRemoteError):
    """The secret was missing or wrong; the bridge closed the connection."""


class BridgeBusyError(BridgeRemoteError):
    """AutoCAD cannot take the request now; :attr:`message` says what the user should do."""

    @property
    def reason(self) -> str:
        return str(self.data.get("reason", ""))

    @property
    def retry_after(self) -> float:
        """Suggested wait in seconds before retrying."""
        return float(self.data.get("retry_after_ms", 1000)) / 1000.0


class BridgeOperationError(BridgeRemoteError):
    """The drawing operation failed inside AutoCAD; :attr:`rolled_back` says if it was undone."""

    @property
    def rolled_back(self) -> bool:
        return bool(self.data.get("rolled_back", False))


_ERROR_TYPES: dict[int, type[BridgeRemoteError]] = {
    ErrorCode.UNAUTHORIZED: BridgeAuthError,
    ErrorCode.BUSY: BridgeBusyError,
    ErrorCode.OPERATION_FAILED: BridgeOperationError,
}


def error_from_payload(error: Any) -> BridgeRemoteError:
    """Turn a JSON-RPC ``error`` member into the matching exception."""
    if not isinstance(error, dict) or not isinstance(error.get("code"), int):
        raise BridgeProtocolError(f"malformed error object: {error!r}")
    code = error["code"]
    data = error.get("data")
    return _ERROR_TYPES.get(code, BridgeRemoteError)(
        code, str(error.get("message", "")), data if isinstance(data, dict) else None
    )


def request(request_id: int | str, method: str, params: dict[str, Any] | None = None) -> dict:
    message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return message


def result_response(request_id: int | str | None, result: Any) -> dict:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(
    request_id: int | str | None, code: int, message: str, data: dict[str, Any] | None = None
) -> dict:
    error: dict[str, Any] = {"code": int(code), "message": message}
    if data is not None:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": request_id, "error": error}


def encode(message: dict) -> bytes:
    """One compact JSON object plus ``\\n`` (JSON escapes any newline inside strings)."""
    return json.dumps(message, separators=(",", ":"), ensure_ascii=False).encode("utf-8") + b"\n"


def decode(line: bytes) -> dict:
    """Parse one line; raises :class:`BridgeProtocolError` unless it is a JSON object."""
    try:
        message = json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeProtocolError(f"invalid JSON line: {exc}") from exc
    if not isinstance(message, dict):
        raise BridgeProtocolError("a message must be a JSON object")
    return message


class LineBuffer:
    """Accumulates byte chunks and yields complete lines, refusing unbounded growth."""

    def __init__(self, max_line_bytes: int = MAX_LINE_BYTES) -> None:
        self._max = max_line_bytes
        self._pending = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        self._pending += chunk
        *lines, rest = self._pending.split(b"\n")
        self._pending = bytearray(rest)
        if len(self._pending) > self._max:
            raise BridgeProtocolError(f"line exceeds {self._max} bytes")
        out = []
        for raw in lines:
            line = bytes(raw.removesuffix(b"\r"))
            if len(line) > self._max:
                raise BridgeProtocolError(f"line exceeds {self._max} bytes")
            out.append(line)
        return out
