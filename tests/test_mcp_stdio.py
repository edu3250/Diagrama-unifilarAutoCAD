"""The server as a host runs it: a real subprocess that speaks MCP over stdin and stdout.

The in-memory tests prove the tools; these prove the transport rules that break stdio servers on
Windows: nothing but JSON-RPC frames on stdout, accents surviving the wire without
``PYTHONUTF8``, a start that fits well inside Claude Code's 30 s window, and the committed
``.mcp.json`` that registers the server.
"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import threading
import time
import tomllib
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client
from mcp.client.stdio import StdioServerParameters

from pvsld.backends.base import sha256_hex
from pvsld.mcp.sandbox import OUTPUT_DIR_ENV
from s1_helpers import GOLDEN_DIR, ROOT, load_example

# Claude Code gives a stdio server 30 s to start. The spike target is 5 s (measured and recorded in
# docs/spikes/s3-mcp-round-trip.md); CI asserts half the host window so a slow shared runner does
# not turn a measurement into a flaky failure.
STARTUP_BUDGET_S = 15.0
GOLDEN = GOLDEN_DIR / "residential_7p7kwp.dxf"


def _environment(output_dir: Path) -> dict[str, str]:
    """The parent environment minus the UTF-8 switches, so the server must cope on its own."""
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONUTF8", "PYTHONIOENCODING"}}
    env[OUTPUT_DIR_ENV] = str(output_dir)
    return env


def _spec(twelve_modules: bool = False) -> dict[str, Any]:
    spec = json.loads(json.dumps(load_example(), default=str))
    if twelve_modules:
        for string in spec["strings"]:
            string["n_series"] = 12
    return spec


def _frame(message: dict[str, Any]) -> bytes:
    return json.dumps(message, ensure_ascii=False).encode("utf-8") + b"\n"


def _converse(
    output_dir: Path, requests: list[dict[str, Any]]
) -> tuple[dict[Any, Any], float, str]:
    """Send ``requests`` to a fresh server and return the responses by id, seconds until the last
    answer, and stderr. Every stdout line must be a JSON-RPC frame."""
    process = subprocess.Popen(
        [sys.executable, "-m", "pvsld.mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=_environment(output_dir),
    )
    watchdog = threading.Timer(90, process.kill)
    watchdog.start()
    responses: dict[Any, Any] = {}
    started = time.perf_counter()
    try:
        assert process.stdin is not None
        assert process.stdout is not None
        assert process.stderr is not None
        pending = {request["id"] for request in requests if "id" in request}
        for request in requests:
            process.stdin.write(_frame(request))
        process.stdin.flush()
        while pending:
            line = process.stdout.readline()
            assert line, f"the server closed stdout; still waiting for {pending}"
            message = json.loads(line.decode("utf-8"))  # a stray print would fail right here
            assert message["jsonrpc"] == "2.0"
            responses[message.get("id")] = message
            pending.discard(message.get("id"))
        elapsed = time.perf_counter() - started
        process.stdin.close()
        stderr = process.stderr.read().decode("utf-8", errors="replace")
        assert process.wait(timeout=30) == 0
        return responses, elapsed, stderr
    finally:
        watchdog.cancel()
        process.kill()


def _handshake() -> list[dict[str, Any]]:
    initialize = {
        "protocolVersion": "2025-06-18",
        "capabilities": {},
        "clientInfo": {"name": "raw-stdio-test", "version": "0"},
    }
    return [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": initialize},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]


def test_stdout_carries_only_frames_and_logs_go_to_stderr(tmp_path: Path) -> None:
    requests = [*_handshake(), {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}]
    responses, elapsed, stderr = _converse(tmp_path / "out", requests)
    names = {tool["name"] for tool in responses[2]["result"]["tools"]}
    assert names == {
        "validate_pv_design",
        "generate_single_line_diagram",
        "list_components",
        "get_component",
        "size_pv_system",
        "design_and_draw",
    }
    assert "serving on stdio" in stderr
    assert elapsed < STARTUP_BUDGET_S


def test_accents_survive_the_wire_without_pythonutf8(tmp_path: Path) -> None:
    call = {
        "name": "validate_pv_design",
        "arguments": {"spec": _spec(twelve_modules=True)},
    }
    requests = [
        *_handshake(),
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": call},
    ]
    responses, _, stderr = _converse(tmp_path / "out", requests)
    result = responses[3]["result"]
    assert result["structuredContent"]["findings"][0]["rule_id"] == "VOLT-001"
    assert "máximo 11 módulos" in result["content"][0]["text"]
    assert "tool=validate_pv_design" in stderr
    assert "máximo" not in stderr, "the audit log must not echo findings or spec data"


def test_a_host_like_client_completes_validate_then_generate(tmp_path: Path) -> None:
    out = tmp_path / "out"
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "pvsld.mcp"],
        env={OUTPUT_DIR_ENV: str(out)},
        cwd=tmp_path,
    )

    async def session() -> tuple[Any, Any, Any]:
        async with Client(parameters) as client:
            refused = await client.call_tool(
                "generate_single_line_diagram", {"spec": _spec(True), "preview": False}
            )
            validated = await client.call_tool("validate_pv_design", {"spec": _spec()})
            generated = await client.call_tool(
                "generate_single_line_diagram", {"spec": _spec(), "preview": False}
            )
            return refused, validated, generated

    refused, validated, generated = anyio.run(session)
    assert refused.is_error
    assert validated.structured_content["ok"] is True
    assert not generated.is_error
    assert generated.structured_content["sha256"] == sha256_hex(GOLDEN.read_bytes())
    assert (out / "PV-2026-0001.dxf").read_bytes() == GOLDEN.read_bytes()


def test_the_default_output_directory_is_out_under_the_working_directory(tmp_path: Path) -> None:
    env = {k: v for k, v in _environment(tmp_path).items() if k != OUTPUT_DIR_ENV}
    parameters = StdioServerParameters(
        command=sys.executable, args=["-m", "pvsld.mcp"], env=env, cwd=tmp_path
    )

    async def session() -> Any:
        async with Client(parameters) as client:
            return await client.call_tool(
                "generate_single_line_diagram", {"spec": _spec(), "preview": False}
            )

    result = anyio.run(session)
    assert not result.is_error
    assert (
        Path(result.structured_content["dxf_path"]).resolve()
        == (tmp_path / "out" / "PV-2026-0001.dxf").resolve()
    )


def test_the_version_flag_exits_before_serving() -> None:
    done = subprocess.run(
        [sys.executable, "-m", "pvsld.mcp", "--version"],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0
    assert done.stdout.startswith("pvsld-mcp ")


# --- registration ------------------------------------------------------------------------------


def test_the_console_script_target_is_importable() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        scripts = tomllib.load(handle)["project"]["scripts"]
    module_name, _, attribute = scripts["pvsld-mcp"].partition(":")
    assert module_name == "pvsld.mcp.server"
    assert callable(getattr(importlib.import_module(module_name), attribute))


def test_mcp_json_registers_the_server_without_machine_specific_paths() -> None:
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    server = config["mcpServers"]["pvsld"]
    assert server["type"] == "stdio"
    assert "pvsld-mcp" in server["command"]
    assert not Path(server["command"]).is_absolute()
    assert server["env"]["PYTHONUTF8"] == "1"
    assert OUTPUT_DIR_ENV in server["env"]
    text = (ROOT / ".mcp.json").read_text(encoding="utf-8")
    assert "\\" not in text, "a committed .mcp.json must not hold Windows paths"
    assert "Users" not in text


@pytest.mark.parametrize("flag", ["--help", "-h"])
def test_help_is_available(flag: str) -> None:
    done = subprocess.run(
        [sys.executable, "-m", "pvsld.mcp", flag],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0
    assert "--output-dir" in done.stdout
