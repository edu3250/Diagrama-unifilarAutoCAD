"""Stage 3.7.1: a client that gave up on ``server/discover`` while the server started still
connects (Copilot CLI falls back to ``initialize`` after about 10 s)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import anyio
import mcp_types as types
import pytest
from mcp.shared.message import SessionMessage

from pvsld.mcp.handshake import DISCOVER, INITIALIZE, forward_what_the_client_awaits

ENVELOPE = {
    "_meta": {
        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
        "io.modelcontextprotocol/clientInfo": {"name": "test", "version": "0"},
        "io.modelcontextprotocol/clientCapabilities": {},
    }
}
SRC = Path(__file__).resolve().parents[1] / "src"
DISCOVERY = {"jsonrpc": "2.0", "id": 0, "method": DISCOVER, "params": ENVELOPE}
HANDSHAKE = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": INITIALIZE,
    "params": {
        "protocolVersion": "2025-11-25",
        "capabilities": {},
        "clientInfo": {"name": "test", "version": "0"},
    },
}
LIST_TOOLS = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": ENVELOPE}


def frame(data: dict[str, Any]) -> SessionMessage:
    return SessionMessage(types.jsonrpc_message_adapter.validate_python(data, by_name=False))


def forwarded(frames: list[tuple[float, Any]], grace_s: float = 0.2) -> list[Any]:
    """What reaches the server when each frame arrives ``delay`` seconds after the one before."""

    async def scenario() -> list[Any]:
        send_in, receive_in = anyio.create_memory_object_stream[Any](10)
        send_out, receive_out = anyio.create_memory_object_stream[Any](10)

        async def client() -> None:
            async with send_in:
                for delay, item in frames:
                    await anyio.sleep(delay)
                    await send_in.send(item)

        async with anyio.create_task_group() as tasks:
            tasks.start_soon(client)
            tasks.start_soon(forward_what_the_client_awaits, receive_in, send_out, grace_s)
            return [item async for item in receive_out]

    return anyio.run(scenario)


def methods(items: list[Any]) -> list[str | None]:
    return [getattr(getattr(item, "message", None), "method", None) for item in items]


def test_a_discovery_the_client_gave_up_on_is_dropped() -> None:
    """A late server finds both requests in the pipe: the client waits for the second."""
    arrived = forwarded([(0, frame(DISCOVERY)), (0, frame(HANDSHAKE)), (0.3, frame(LIST_TOOLS))])
    assert methods(arrived) == [INITIALIZE, "tools/list"]


def test_a_discovery_the_client_waits_for_is_answered() -> None:
    """A server that is ready in time: nothing follows the discovery until it is answered."""
    arrived = forwarded([(0, frame(DISCOVERY)), (0.5, frame(LIST_TOOLS))])
    assert methods(arrived) == [DISCOVER, "tools/list"]


def test_whatever_follows_a_discovery_at_once_is_kept_unless_it_is_the_handshake() -> None:
    arrived = forwarded([(0, frame(DISCOVERY)), (0, frame(LIST_TOOLS))])
    assert methods(arrived) == [DISCOVER, "tools/list"]


def test_the_older_handshake_alone_passes_untouched() -> None:
    arrived = forwarded([(0, frame(HANDSHAKE)), (0, frame(LIST_TOOLS))])
    assert methods(arrived) == [INITIALIZE, "tools/list"]


def test_only_the_first_frame_is_looked_at() -> None:
    """A discovery later in a session is the SDK's business."""
    arrived = forwarded([(0, frame(LIST_TOOLS)), (0, frame(DISCOVERY)), (0, frame(HANDSHAKE))])
    assert methods(arrived) == ["tools/list", DISCOVER, INITIALIZE]


def test_a_connection_closed_after_the_discovery_still_delivers_it() -> None:
    assert methods(forwarded([(0, frame(DISCOVERY))])) == [DISCOVER]
    assert forwarded([]) == []


def test_an_unreadable_line_is_passed_on_like_any_frame() -> None:
    broken = ValueError("not JSON")
    arrived = forwarded([(0, frame(DISCOVERY)), (0, broken)])
    assert arrived[1] is broken
    assert methods(arrived) == [DISCOVER, None]


def _answers(process: subprocess.Popen[bytes], count: int) -> list[dict[str, Any]]:
    assert process.stdout is not None
    return [json.loads(process.stdout.readline()) for _ in range(count)]


@pytest.mark.parametrize("late", [True, False])
def test_the_real_server_over_stdio(late: bool, tmp_path: Path) -> None:
    """The whole path: a server process, the SDK's transport and the filter.

    ``late``: both requests are in the pipe before the server reads (the client gave up); the
    answer must be the handshake's, not a refusal of it.
    """
    process = subprocess.Popen(
        [sys.executable, "-c", "import sys; from pvsld.mcp.server import main; sys.exit(main())"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(SRC)},  # this checkout, whatever is installed
    )
    assert process.stdin is not None
    try:
        process.stdin.write((json.dumps(DISCOVERY) + "\n").encode())
        if late:
            process.stdin.write((json.dumps(HANDSHAKE) + "\n").encode())
        process.stdin.flush()
        (answer,) = _answers(process, 1)
        assert "error" not in answer, answer
        if late:
            assert answer["id"] == HANDSHAKE["id"]
            assert answer["result"]["protocolVersion"] == "2025-11-25"
            assert answer["result"]["serverInfo"]["name"] == "pvsld"
        else:
            assert answer["id"] == DISCOVERY["id"]
            assert "tools" in answer["result"]["capabilities"]
    finally:
        process.stdin.close()
        deadline = time.monotonic() + 20
        while process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.1)
        if process.poll() is None:
            process.kill()
    assert process.returncode == 0
