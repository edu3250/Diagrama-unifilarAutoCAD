"""Byte streams that carry the bridge protocol, each with per-operation timeouts.

:class:`WindowsPipeStream` is the real transport (overlapped I/O on a Windows named pipe, so a
silent AutoCAD can never block the caller forever). :class:`SocketStream` exists so the protocol
client can be tested against an in-process fake server on any OS, including Linux CI.
"""

from __future__ import annotations

import contextlib
import socket
import sys
import time
from typing import Protocol

from pvsld.transports.protocol import BridgeConnectionError

READ_CHUNK = 64 * 1024


class ByteStream(Protocol):
    """A bidirectional byte stream. Timeouts are in seconds; ``None`` blocks."""

    def send(self, data: bytes, timeout: float | None) -> None:
        """Write all of ``data``; raise :class:`TimeoutError` if that takes longer than allowed."""
        ...

    def recv(self, max_bytes: int, timeout: float | None) -> bytes:
        """Return up to ``max_bytes`` (``b""`` at end of stream) or raise :class:`TimeoutError`."""
        ...

    def close(self) -> None: ...


class SocketStream:
    """A connected TCP socket (used by tests and by the fake bridge server)."""

    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock

    @classmethod
    def connect(cls, host: str, port: int, timeout: float) -> SocketStream:
        try:
            return cls(socket.create_connection((host, port), timeout=timeout))
        except OSError as exc:
            raise BridgeConnectionError(f"cannot connect to {host}:{port}: {exc}") from exc

    def send(self, data: bytes, timeout: float | None) -> None:
        self._sock.settimeout(timeout)
        try:
            self._sock.sendall(data)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError) as exc:
            raise BridgeConnectionError(f"connection lost while sending: {exc}") from exc

    def recv(self, max_bytes: int, timeout: float | None) -> bytes:
        self._sock.settimeout(timeout)
        try:
            return self._sock.recv(max_bytes)
        except (ConnectionResetError, ConnectionAbortedError):
            return b""

    def close(self) -> None:
        with contextlib.suppress(OSError):  # the peer may already be gone
            self._sock.shutdown(socket.SHUT_RDWR)
        self._sock.close()


if sys.platform == "win32":
    import pywintypes
    import win32event
    import win32file
    import win32pipe
    import winerror

    _BROKEN = {
        winerror.ERROR_BROKEN_PIPE,
        winerror.ERROR_PIPE_NOT_CONNECTED,
        winerror.ERROR_NO_DATA,
    }

    def _millis(timeout: float | None) -> int:
        return win32event.INFINITE if timeout is None else max(0, int(timeout * 1000))

    class WindowsPipeStream:
        """A named-pipe handle opened for overlapped I/O, so every read and write can time out."""

        def __init__(self, handle: int | pywintypes.HANDLE) -> None:
            self._handle = handle
            self._read_event = win32event.CreateEvent(None, True, False, None)
            self._write_event = win32event.CreateEvent(None, True, False, None)

        @property
        def handle(self) -> pywintypes.HANDLE:
            return self._handle

        @classmethod
        def connect(
            cls, pipe_name: str, timeout: float, *, expected_server_pid: int | None = None
        ) -> WindowsPipeStream:
            """Open ``\\\\.\\pipe\\<pipe_name>``; optionally verify which process serves it."""
            path = rf"\\.\pipe\{pipe_name}"
            deadline = time.monotonic() + timeout
            grace = 0.25
            while True:
                try:
                    handle = win32file.CreateFile(
                        path,
                        win32file.GENERIC_READ | win32file.GENERIC_WRITE,
                        0,
                        None,
                        win32file.OPEN_EXISTING,
                        win32file.FILE_FLAG_OVERLAPPED,
                        None,
                    )
                    break
                except pywintypes.error as exc:
                    remaining = deadline - time.monotonic()
                    if exc.winerror == winerror.ERROR_PIPE_BUSY and remaining > 0:
                        with contextlib.suppress(pywintypes.error):  # timed out: loop decides
                            win32pipe.WaitNamedPipe(path, _millis(remaining))
                        continue
                    if (
                        exc.winerror == winerror.ERROR_FILE_NOT_FOUND
                        and grace > 0
                        and remaining > 0
                    ):
                        # The server re-creates its listening instance right after each
                        # accept; a client arriving in that gap sees "not found" briefly.
                        time.sleep(0.02)
                        grace -= 0.02
                        continue
                    if exc.winerror == winerror.ERROR_FILE_NOT_FOUND:
                        raise BridgeConnectionError(
                            f"no bridge is listening on {path}; start AutoCAD and NETLOAD the "
                            "pvsld plug-in (docs/spikes/s2-autocad-connectivity.md)"
                        ) from exc
                    raise BridgeConnectionError(f"cannot open {path}: {exc.strerror}") from exc

            stream = cls(handle)
            if expected_server_pid is not None:
                server_pid = win32pipe.GetNamedPipeServerProcessId(handle)
                if server_pid != expected_server_pid:
                    stream.close()
                    raise BridgeConnectionError(
                        f"{path} is served by process {server_pid}, not by AutoCAD "
                        f"(pid {expected_server_pid}); refusing to send the secret"
                    )
            return stream

        def send(self, data: bytes, timeout: float | None) -> None:
            view = memoryview(data)
            deadline = None if timeout is None else time.monotonic() + timeout
            while view:
                remaining = None if deadline is None else deadline - time.monotonic()
                written = self._overlapped(self._write_event, remaining, write=view)
                view = view[written:]

        def recv(self, max_bytes: int, timeout: float | None) -> bytes:
            buffer = win32file.AllocateReadBuffer(max_bytes)
            count = self._overlapped(self._read_event, timeout, read=buffer)
            return bytes(buffer[:count])

        def _overlapped(
            self,
            event: pywintypes.HANDLE,
            timeout: float | None,
            *,
            read: object | None = None,
            write: memoryview | None = None,
        ) -> int:
            overlapped = pywintypes.OVERLAPPED()
            overlapped.hEvent = event
            win32event.ResetEvent(event)
            try:
                if read is not None:
                    win32file.ReadFile(self._handle, read, overlapped)
                else:
                    win32file.WriteFile(self._handle, bytes(write), overlapped)
            except pywintypes.error as exc:
                if exc.winerror in _BROKEN:
                    if read is not None:
                        return 0
                    raise BridgeConnectionError("the bridge closed the pipe") from exc
                raise BridgeConnectionError(f"pipe I/O failed: {exc.strerror}") from exc

            if timeout is not None and timeout <= 0:
                timeout = 0.0
            if win32event.WaitForSingleObject(event, _millis(timeout)) == win32event.WAIT_TIMEOUT:
                win32file.CancelIo(self._handle)
                try:
                    count = win32file.GetOverlappedResult(self._handle, overlapped, True)
                except pywintypes.error as exc:
                    if exc.winerror == winerror.ERROR_OPERATION_ABORTED:
                        raise TimeoutError("pipe I/O timed out") from exc
                    if exc.winerror in _BROKEN and read is not None:
                        return 0
                    raise BridgeConnectionError(f"pipe I/O failed: {exc.strerror}") from exc
                return count  # completed just before the cancel took effect

            try:
                return win32file.GetOverlappedResult(self._handle, overlapped, True)
            except pywintypes.error as exc:
                if exc.winerror in _BROKEN:
                    if read is not None:
                        return 0
                    raise BridgeConnectionError("the bridge closed the pipe") from exc
                raise BridgeConnectionError(f"pipe I/O failed: {exc.strerror}") from exc

        def close(self) -> None:
            for handle in (self._handle, self._read_event, self._write_event):
                if handle is not None:
                    win32file.CloseHandle(handle)
            self._handle = self._read_event = self._write_event = None
