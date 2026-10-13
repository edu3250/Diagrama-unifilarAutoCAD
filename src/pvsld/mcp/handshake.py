"""Serve over stdio for a client that gave up on its first request while the server started.

Copilot CLI opens a connection with ``server/discover`` (protocol 2026-07-28). When no answer comes
in about 10 s it sends the older ``initialize`` and waits for that one. The MCP SDK fixes a
connection to the protocol of its first frame, so it answers the ``server/discover`` nobody is
waiting for any more and refuses the ``initialize``: the client marks the server as failed. A
server started by ``uvx`` is often ready later than that, and always on its first start, which
downloads its dependencies (Stage 3.7, measured with Copilot CLI 1.0.96).

Both requests are already in the pipe when a late server starts to read. The filter here looks at
the first frame; when it is ``server/discover`` it waits a moment for the next one, and when that is
``initialize`` it drops the discovery, so the SDK serves the handshake the client is waiting for.
A server that is ready in time gets the discovery alone and answers it, a fraction of a second
later than before.
"""

from __future__ import annotations

from typing import Any, Protocol

import anyio
from mcp.server import MCPServer
from mcp.server.stdio import stdio_server
from mcp.shared._context_streams import create_context_streams
from mcp.shared.message import SessionMessage

__all__ = ["DISCOVER", "GRACE_S", "INITIALIZE", "forward_what_the_client_awaits", "serve_stdio"]

DISCOVER = "server/discover"
INITIALIZE = "initialize"
GRACE_S = 0.2
"""How long the frame after a discovery may take to be read from the pipe. A client that is
waiting for the discovery sends nothing in that time; one that gave up already has."""


class _Source(Protocol):
    async def receive(self) -> Any: ...


class _Sink(Protocol):
    async def send(self, item: Any) -> None: ...

    async def aclose(self) -> None: ...


def _method(item: object) -> str | None:
    """The JSON-RPC method of a frame; ``None`` for a response or an unreadable line."""
    return getattr(getattr(item, "message", None), "method", None)


async def forward_what_the_client_awaits(
    source: _Source, sink: _Sink, grace_s: float = GRACE_S
) -> None:
    """Copy ``source`` to ``sink`` without a first ``server/discover`` the client gave up on."""
    try:
        held = [await source.receive()]
        closed = False
        if _method(held[0]) == DISCOVER:
            with anyio.move_on_after(grace_s):
                try:
                    held.append(await source.receive())
                except anyio.EndOfStream:
                    closed = True
            if len(held) == 2 and _method(held[1]) == INITIALIZE:
                del held[0]
        for item in held:
            await sink.send(item)
        while not closed:
            await sink.send(await source.receive())
    except (anyio.EndOfStream, anyio.ClosedResourceError):
        pass
    finally:
        await sink.aclose()


async def serve_stdio(server: MCPServer) -> None:
    """``MCPServer.run_stdio_async`` with the filter between the transport and the server."""
    lowlevel = server._lowlevel_server
    async with stdio_server() as (read_stream, write_stream):
        send, receive = create_context_streams[SessionMessage | Exception](0)
        async with anyio.create_task_group() as tasks:
            tasks.start_soon(forward_what_the_client_awaits, read_stream, send)
            await lowlevel.run(receive, write_stream, lowlevel.create_initialization_options())
            tasks.cancel_scope.cancel()
