"""The MCP server, driven through an in-memory client: the same protocol Claude Code speaks.

``Client(server)`` connects to the ``MCPServer`` object in-process (no subprocess, no port), so
these tests cover tool and resource listing, structured results, tool errors, the output sandbox
and the size of results against the host budget.
"""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypeVar

import anyio
import pytest
from mcp import Client
from mcp.types import CallToolResult, ImageContent, TextContent

import pvsld.mcp
from pvsld.backends.base import sha256_hex
from pvsld.core.model import RULEPACK_ID, export_json_schema
from pvsld.core.rules import rulepack_catalogue
from pvsld.mcp import server as server_module
from pvsld.mcp.models import MAX_FINDINGS
from pvsld.mcp.sandbox import OutputSandbox
from pvsld.mcp.server import (
    GENERATE_DESCRIPTION,
    INSTRUCTIONS,
    RULEPACK_URI,
    SCHEMA_URI,
    SYMBOLS_URI,
    VALIDATE_DESCRIPTION,
    create_server,
)
from pvsld.symbols import symbol_catalogue
from s1_helpers import GOLDEN_DIR, load_example

T = TypeVar("T")

GOLDEN = GOLDEN_DIR / "residential_7p7kwp.dxf"
GENERATE = "generate_single_line_diagram"
VALIDATE = "validate_pv_design"
# Claude Code stops a tool result at 25k tokens; four characters per token is the conservative
# estimate (real text of this kind is closer to three, but the image is base64 that counts as text).
TOKEN_BUDGET = 25_000


def run_client(server: Any, scenario: Callable[[Client], Awaitable[T]]) -> T:
    async def runner() -> T:
        async with Client(server) as client:
            return await scenario(client)

    return anyio.run(runner)


def call(server: Any, tool: str, arguments: dict[str, Any]) -> CallToolResult:
    return run_client(server, lambda client: client.call_tool(tool, arguments))


def example_spec() -> dict[str, Any]:
    """The sample as an MCP client sends it: plain JSON (YAML dates become strings)."""
    return json.loads(json.dumps(load_example(), default=str))


def spec_with_twelve_modules() -> dict[str, Any]:
    spec = example_spec()
    for string in spec["strings"]:
        string["n_series"] = 12
    return spec


def text_of(result: CallToolResult) -> str:
    texts = [block.text for block in result.content if isinstance(block, TextContent)]
    assert len(texts) == 1
    return texts[0]


def images_of(result: CallToolResult) -> list[ImageContent]:
    return [block for block in result.content if isinstance(block, ImageContent)]


def estimated_tokens(result: CallToolResult) -> float:
    return len(result.model_dump_json(by_alias=True)) / 4


@pytest.fixture
def sandbox(tmp_path: Path) -> OutputSandbox:
    return OutputSandbox.at(tmp_path / "out")


@pytest.fixture
def server(sandbox: OutputSandbox) -> Any:
    return create_server(sandbox)


@pytest.fixture(scope="module")
def generated(tmp_path_factory: pytest.TempPathFactory) -> tuple[OutputSandbox, CallToolResult]:
    """One real generation with the preview (about 3 s), shared by the assertions on its result."""
    box = OutputSandbox.at(tmp_path_factory.mktemp("generated") / "out")
    result = call(create_server(box), GENERATE, {"spec": example_spec()})
    return box, result


# --- the surface -------------------------------------------------------------------------------


def test_the_server_lists_exactly_the_two_workflow_tools(server: Any) -> None:
    tools = run_client(server, lambda client: client.list_tools()).tools
    assert sorted(tool.name for tool in tools) == [GENERATE, VALIDATE]


def test_the_tool_annotations_are_honest(server: Any) -> None:
    tools = {tool.name: tool for tool in run_client(server, lambda c: c.list_tools()).tools}
    validate = tools[VALIDATE].annotations
    assert validate is not None
    assert validate.read_only_hint is True
    assert validate.open_world_hint is False
    generate = tools[GENERATE].annotations
    assert generate is not None
    assert generate.read_only_hint is False
    assert generate.destructive_hint is False
    assert generate.idempotent_hint is True
    assert generate.open_world_hint is False


def test_every_tool_advertises_an_output_schema(server: Any) -> None:
    tools = run_client(server, lambda client: client.list_tools()).tools
    for tool in tools:
        assert tool.output_schema is not None
        assert {"ok", "next_step"} <= set(tool.output_schema["properties"])


def test_descriptions_fit_the_claude_code_truncation_limit(server: Any) -> None:
    tools = run_client(server, lambda client: client.list_tools()).tools
    for tool in tools:
        assert tool.description
        assert len(tool.description) < 2048
    assert len(INSTRUCTIONS) < 2048
    assert VALIDATE_DESCRIPTION.startswith("Check a PV system spec")
    assert GENERATE_DESCRIPTION.startswith("Draw the A3")


def test_no_tool_accepts_a_path_or_code(server: Any) -> None:
    forbidden = {"path", "output", "output_path", "file", "filename", "directory", "command"}
    forbidden |= {"code", "script", "lisp", "expression"}
    tools = run_client(server, lambda client: client.list_tools()).tools
    for tool in tools:
        assert not forbidden & set(tool.input_schema["properties"]), tool.name


def test_the_spec_parameter_points_to_the_schema_resource(server: Any) -> None:
    tools = {tool.name: tool for tool in run_client(server, lambda c: c.list_tools()).tools}
    for tool in tools.values():
        spec = tool.input_schema["properties"]["spec"]
        assert spec["type"] == "object"
        assert SCHEMA_URI in spec["description"]
        assert "project" in spec["description"]
    assert tools[GENERATE].input_schema["required"] == ["spec"]


def test_the_instructions_tell_claude_to_validate_first(server: Any) -> None:
    async def read_instructions(client: Client) -> str | None:
        return client.instructions

    instructions = run_client(server, read_instructions)
    assert instructions is not None
    assert instructions == INSTRUCTIONS
    assert instructions.index(VALIDATE) < instructions.index(GENERATE)
    assert "Never invent" in instructions


def test_the_server_lists_the_three_resources(server: Any) -> None:
    resources = run_client(server, lambda client: client.list_resources()).resources
    assert {str(resource.uri) for resource in resources} == {SCHEMA_URI, RULEPACK_URI, SYMBOLS_URI}
    assert {resource.mime_type for resource in resources} == {"application/json"}


def _read_json(server: Any, uri: str) -> Any:
    contents = run_client(server, lambda client: client.read_resource(uri)).contents
    assert len(contents) == 1
    return json.loads(contents[0].text)  # type: ignore[union-attr]


def test_the_schema_resource_is_the_model_json_schema(server: Any) -> None:
    schema = _read_json(server, SCHEMA_URI)
    assert schema == export_json_schema()
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_the_rulepack_resource_catalogues_the_rules(server: Any) -> None:
    pack = _read_json(server, RULEPACK_URI)
    assert pack["rulepack"] == RULEPACK_ID
    assert pack["rules"] == json.loads(json.dumps(rulepack_catalogue()))
    assert "VOLT-001" in {rule["id"] for rule in pack["rules"]}


def test_the_symbol_resource_catalogues_the_blocks(server: Any) -> None:
    assert _read_json(server, SYMBOLS_URI) == json.loads(json.dumps(symbol_catalogue()))


# --- validate_pv_design ------------------------------------------------------------------------


def test_validate_accepts_the_sample(server: Any) -> None:
    result = call(server, VALIDATE, {"spec": example_spec()})
    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["ok"] is True
    assert result.structured_content["errors"] == 0
    assert result.structured_content["rulepack"] == RULEPACK_ID
    assert result.structured_content["derived"]["kwp_total"] == 7.7
    assert "generate_single_line_diagram" in result.structured_content["next_step"]
    assert text_of(result).startswith("OK: 0 errors")


def test_validate_reports_volt_001_for_twelve_modules_per_string(server: Any) -> None:
    result = call(server, VALIDATE, {"spec": spec_with_twelve_modules()})
    assert not result.is_error, "findings are a normal result, not a tool error"
    assert result.structured_content is not None
    content = result.structured_content
    assert content["ok"] is False
    assert content["errors"] == 2
    findings = content["findings"]
    assert [(f["rule_id"], f["subject"], f["severity"]) for f in findings] == [
        ("VOLT-001", "S1", "error"),
        ("VOLT-001", "S2", "error"),
    ]
    first = findings[0]
    assert "máximo 11 módulos" in first["message_es"]
    assert first["mx_ids"] == ["MX-C02"]
    assert any("690-7" in cite for cite in first["cites"])
    assert "validate_pv_design" in content["next_step"]
    # Hosts that show only the text content must still get the rule, subject and the fix.
    text = text_of(result)
    assert "VOLT-001 S1" in text
    assert "máximo 11 módulos" in text


def test_validate_turns_schema_problems_into_gen_001_findings(server: Any) -> None:
    result = call(server, VALIDATE, {"spec": {}})
    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["ok"] is False
    assert "derived" not in result.structured_content
    findings = result.structured_content["findings"]
    assert findings
    assert {finding["rule_id"] for finding in findings} == {"GEN-001"}
    assert "project" in {finding["subject"] for finding in findings}


def test_validate_caps_a_flood_of_findings(server: Any) -> None:
    spec = example_spec()
    spec["strings"] = [{} for _ in range(100)]
    result = call(server, VALIDATE, {"spec": spec})
    assert result.structured_content is not None
    assert len(result.structured_content["findings"]) == MAX_FINDINGS
    assert result.structured_content["findings_total"] > MAX_FINDINGS
    assert "more finding(s)" in text_of(result)
    assert estimated_tokens(result) < TOKEN_BUDGET


def test_validate_puts_errors_before_warnings(server: Any) -> None:
    spec = spec_with_twelve_modules()
    result = call(server, VALIDATE, {"spec": spec})
    assert result.structured_content is not None
    severities = [finding["severity"] for finding in result.structured_content["findings"]]
    assert severities == sorted(severities, key=["error", "warning", "info"].index)


def test_validate_rejects_a_spec_that_is_not_an_object(server: Any) -> None:
    result = call(server, VALIDATE, {"spec": "residential_7p7kwp.yaml"})
    assert result.is_error
    assert "spec" in text_of(result)


def test_validate_does_not_touch_the_file_system(server: Any, sandbox: OutputSandbox) -> None:
    call(server, VALIDATE, {"spec": example_spec()})
    assert not sandbox.root.exists()


# --- generate_single_line_diagram --------------------------------------------------------------


def test_generate_writes_the_golden_dxf_into_the_sandbox(
    generated: tuple[OutputSandbox, CallToolResult],
) -> None:
    box, result = generated
    assert not result.is_error
    content = result.structured_content
    assert content is not None
    dxf = box.root / "PV-2026-0001.dxf"
    assert content["dxf_path"] == str(dxf)
    assert dxf.is_file()
    assert content["sha256"] == sha256_hex(GOLDEN.read_bytes())
    assert dxf.read_bytes() == GOLDEN.read_bytes()
    assert content["size_bytes"] == dxf.stat().st_size
    assert content["unchanged"] is False


def test_generate_reports_the_read_back_verification(
    generated: tuple[OutputSandbox, CallToolResult],
) -> None:
    _, result = generated
    assert result.structured_content is not None
    readback = result.structured_content["readback"]
    assert readback["ok"] is True
    assert readback["audit"] == {"errors": 0, "fixes": 0}
    assert readback["dangling_ports"] == []
    assert readback["entities_on_layer_0"] == 0
    assert readback["problems"] == []
    checked, _, total = readback["attribute_roundtrip"].partition("/")
    assert checked == total
    assert sum(readback["inserts_per_block"].values()) > 0


def test_generate_returns_a_handle_that_names_the_drawing(
    generated: tuple[OutputSandbox, CallToolResult],
) -> None:
    _, result = generated
    assert result.structured_content is not None
    sha = result.structured_content["sha256"]
    assert result.structured_content["drawing_id"] == f"PV-2026-0001-{sha[:8]}"


def test_generate_attaches_a_png_preview_and_saves_the_full_resolution_one(
    generated: tuple[OutputSandbox, CallToolResult],
) -> None:
    box, result = generated
    (image,) = images_of(result)
    assert image.mime_type == "image/png"
    assert base64.b64decode(image.data).startswith(b"\x89PNG")
    saved = box.root / "PV-2026-0001.png"
    assert saved.is_file()
    assert saved.stat().st_size > len(base64.b64decode(image.data))
    assert result.structured_content is not None
    assert result.structured_content["png_path"] == str(saved)
    assert "attached" in result.structured_content["preview"]


def test_the_generate_result_stays_under_the_token_budget(
    generated: tuple[OutputSandbox, CallToolResult],
) -> None:
    _, result = generated
    assert estimated_tokens(result) < TOKEN_BUDGET
    # The text the model reads next to the image is small on its own.
    assert len(text_of(result)) < 3_000


def test_the_generate_text_carries_what_a_text_only_host_needs(
    generated: tuple[OutputSandbox, CallToolResult],
) -> None:
    _, result = generated
    text = text_of(result)
    assert "drawing_id: PV-2026-0001-" in text
    assert "dxf:" in text
    assert "sha256:" in text
    assert "attributes " in text


def test_nothing_but_the_published_files_is_left_in_the_sandbox(
    generated: tuple[OutputSandbox, CallToolResult],
) -> None:
    box, _ = generated
    assert sorted(path.name for path in box.root.iterdir()) == [
        "PV-2026-0001.dxf",
        "PV-2026-0001.png",
    ]


def test_generate_without_a_preview_returns_no_image_and_no_png(
    server: Any, sandbox: OutputSandbox
) -> None:
    result = call(server, GENERATE, {"spec": example_spec(), "preview": False})
    assert not result.is_error
    assert images_of(result) == []
    assert result.structured_content is not None
    assert "png_path" not in result.structured_content
    assert result.structured_content["preview"] == "not requested"
    assert [path.name for path in sandbox.root.iterdir()] == ["PV-2026-0001.dxf"]


def test_generate_refuses_an_invalid_spec_with_the_findings(
    server: Any, sandbox: OutputSandbox
) -> None:
    result = call(server, GENERATE, {"spec": spec_with_twelve_modules()})
    assert result.is_error
    assert result.structured_content is not None
    assert result.structured_content["ok"] is False
    findings = result.structured_content["validation"]["findings"]
    assert [(f["rule_id"], f["subject"]) for f in findings] == [
        ("VOLT-001", "S1"),
        ("VOLT-001", "S2"),
    ]
    text = text_of(result)
    assert text.startswith("REFUSED: nothing was written.")
    assert "VOLT-001 S1" in text
    assert "máximo 11 módulos" in text
    assert images_of(result) == []
    assert not sandbox.root.exists() or list(sandbox.root.iterdir()) == []


def test_generate_is_corrected_by_the_same_loop_claude_runs(server: Any) -> None:
    refused = call(server, GENERATE, {"spec": spec_with_twelve_modules(), "preview": False})
    assert refused.is_error
    fixed = spec_with_twelve_modules()
    for string in fixed["strings"]:
        string["n_series"] = 7
    assert call(server, VALIDATE, {"spec": fixed}).structured_content["ok"] is True  # type: ignore[index]
    accepted = call(server, GENERATE, {"spec": fixed, "preview": False})
    assert not accepted.is_error
    assert accepted.structured_content is not None
    assert accepted.structured_content["sha256"] == sha256_hex(GOLDEN.read_bytes())


UNSAFE_NAMES = [
    "../evil",
    "..\\evil",
    "..",
    "/etc/passwd",
    "C:\\Windows\\evil",
    "C:evil",
    "\\\\server\\share\\evil",
    "sub/dir",
    "name.dxf",
    "CON",
    "nul",
    "",
    "x" * 65,
    "a\x00b",
]


@pytest.mark.parametrize("name", UNSAFE_NAMES)
def test_a_name_that_could_leave_the_sandbox_is_a_tool_error(
    server: Any, sandbox: OutputSandbox, name: str
) -> None:
    result = call(server, GENERATE, {"spec": example_spec(), "name": name, "preview": False})
    assert result.is_error
    assert "invalid name" in text_of(result)
    assert not sandbox.root.exists()
    assert list(sandbox.root.parent.iterdir()) == []


def test_generate_never_writes_outside_the_sandbox(server: Any, sandbox: OutputSandbox) -> None:
    call(server, GENERATE, {"spec": example_spec(), "name": "plano", "preview": False})
    everything = set(sandbox.root.parent.rglob("*"))
    assert everything == {sandbox.root, sandbox.root / "plano.dxf"}


def test_a_custom_name_names_the_files_and_the_handle(server: Any, sandbox: OutputSandbox) -> None:
    result = call(server, GENERATE, {"spec": example_spec(), "name": "plano-1", "preview": False})
    assert (sandbox.root / "plano-1.dxf").is_file()
    assert result.structured_content is not None
    assert result.structured_content["drawing_id"].startswith("plano-1-")


def test_the_default_name_comes_from_the_project_id(server: Any, sandbox: OutputSandbox) -> None:
    spec = example_spec()
    spec["project"]["id"] = "PV 2026/0007"
    call(server, GENERATE, {"spec": spec, "preview": False})
    assert (sandbox.root / "PV_2026_0007.dxf").is_file()


def test_generating_the_same_spec_twice_is_idempotent(server: Any, sandbox: OutputSandbox) -> None:
    arguments = {"spec": example_spec(), "preview": False}
    first = call(server, GENERATE, arguments)
    second = call(server, GENERATE, arguments)
    assert not second.is_error
    assert first.structured_content is not None
    assert second.structured_content is not None
    assert first.structured_content["unchanged"] is False
    assert second.structured_content["unchanged"] is True
    assert second.structured_content["sha256"] == first.structured_content["sha256"]
    assert "unchanged" in text_of(second)


def _revised_spec() -> dict[str, Any]:
    spec = copy.deepcopy(example_spec())
    spec["title_block"]["revision"] = "B"
    return spec


def test_a_different_drawing_does_not_replace_an_existing_one_by_default(
    server: Any, sandbox: OutputSandbox
) -> None:
    call(server, GENERATE, {"spec": example_spec(), "preview": False})
    target = sandbox.root / "PV-2026-0001.dxf"
    before = target.read_bytes()
    result = call(server, GENERATE, {"spec": _revised_spec(), "preview": False})
    assert result.is_error
    assert "overwrite=true" in text_of(result)
    assert target.read_bytes() == before
    assert sorted(path.name for path in sandbox.root.iterdir()) == ["PV-2026-0001.dxf"]


def test_overwrite_replaces_the_drawing_when_asked(server: Any, sandbox: OutputSandbox) -> None:
    call(server, GENERATE, {"spec": example_spec(), "preview": False})
    target = sandbox.root / "PV-2026-0001.dxf"
    before = target.read_bytes()
    result = call(server, GENERATE, {"spec": _revised_spec(), "overwrite": True, "preview": False})
    assert not result.is_error
    assert result.structured_content is not None
    assert result.structured_content["unchanged"] is False
    assert target.read_bytes() != before
    assert sha256_hex(target.read_bytes()) == result.structured_content["sha256"]


def test_two_generations_at_once_do_not_interfere(server: Any, sandbox: OutputSandbox) -> None:
    async def scenario(client: Client) -> list[CallToolResult]:
        results: list[CallToolResult] = []

        async def one(name: str) -> None:
            results.append(
                await client.call_tool(
                    GENERATE, {"spec": example_spec(), "name": name, "preview": False}
                )
            )

        async with anyio.create_task_group() as group:
            for name in ("uno", "dos", "tres"):
                group.start_soon(one, name)
        return results

    results = run_client(server, scenario)
    assert [result.is_error for result in results] == [False, False, False]
    digests = {sha256_hex(path.read_bytes()) for path in sandbox.root.glob("*.dxf")}
    assert digests == {sha256_hex(GOLDEN.read_bytes())}
    assert not any(path.name.startswith(".") for path in sandbox.root.iterdir())


# --- failure paths -----------------------------------------------------------------------------


def test_a_file_that_cannot_be_replaced_is_an_actionable_tool_error(
    server: Any, sandbox: OutputSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    def locked(self: Path, target: Path) -> Path:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(Path, "replace", locked)
    result = call(server, GENERATE, {"spec": example_spec(), "preview": False})
    assert result.is_error
    assert "open in AutoCAD" in text_of(result)
    assert list(sandbox.root.iterdir()) == []


def test_a_write_failure_inside_the_core_is_a_tool_error(
    server: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    def disk_full(*args: object, **kwargs: object) -> None:
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(server_module.service, "generate_single_line_diagram", disk_full)
    result = call(server, GENERATE, {"spec": example_spec(), "preview": False})
    assert result.is_error
    assert "cannot write the drawing" in text_of(result)


def test_a_drawing_that_fails_read_back_is_discarded(
    server: Any, sandbox: OutputSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = server_module.service.generate_single_line_diagram

    def corrupt(*args: Any, **kwargs: Any) -> Any:
        result = original(*args, **kwargs)
        broken = dataclasses.replace(result.readback, problems=("synthetic: dangling port X",))
        return dataclasses.replace(result, ok=False, readback=broken)

    monkeypatch.setattr(server_module.service, "generate_single_line_diagram", corrupt)
    result = call(server, GENERATE, {"spec": example_spec(), "preview": False})
    assert result.is_error
    text = text_of(result)
    assert text.startswith("FAILED: the DXF did not pass read-back verification")
    assert "problem: synthetic: dangling port X" in text
    assert "defect of the generator" in text
    assert list(sandbox.root.iterdir()) == []


def test_a_preview_that_does_not_fit_is_omitted_not_fatal(
    server: Any, sandbox: OutputSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(server_module, "shrink_png", lambda png, max_bytes: None)
    result = call(server, GENERATE, {"spec": example_spec()})
    assert not result.is_error
    assert images_of(result) == []
    assert result.structured_content is not None
    assert "omitted" in result.structured_content["preview"]
    assert (sandbox.root / "PV-2026-0001.png").is_file()


def test_an_unknown_tool_is_a_tool_error(server: Any) -> None:
    result = call(server, "execute_lisp", {"code": '(command "LINE")'})
    assert result.is_error
    assert "Unknown tool" in text_of(result)


# --- start-up helpers --------------------------------------------------------------------------


def test_the_package_exposes_the_server_factory_lazily() -> None:
    assert pvsld.mcp.create_server is create_server
    assert pvsld.mcp.main is server_module.main
    with pytest.raises(AttributeError, match="no_such_name"):
        _ = pvsld.mcp.no_such_name  # type: ignore[attr-defined]


def test_main_serves_over_stdio_from_the_chosen_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    class FakeServer:
        def run(self, transport: str) -> None:
            seen["transport"] = transport

    def fake_create_server(sandbox: OutputSandbox | None) -> FakeServer:
        seen["sandbox"] = sandbox
        return FakeServer()

    monkeypatch.setattr(server_module, "configure_logging", lambda level: seen.update(level=level))
    monkeypatch.setattr(server_module, "create_server", fake_create_server)
    assert server_module.main(["--output-dir", str(tmp_path / "x"), "--log-level", "DEBUG"]) == 0
    assert seen["transport"] == "stdio"
    assert seen["level"] == "DEBUG"
    assert seen["sandbox"].root == (tmp_path / "x").resolve()


def test_main_without_an_output_directory_leaves_the_choice_to_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, Any] = {}

    class FakeServer:
        def run(self, transport: str) -> None:
            seen["transport"] = transport

    monkeypatch.setattr(server_module, "configure_logging", lambda level: None)
    monkeypatch.setattr(
        server_module, "create_server", lambda sandbox: seen.update(box=sandbox) or FakeServer()
    )
    assert server_module.main([]) == 0
    assert seen["box"] is None


def test_logging_is_sent_to_stderr_never_stdout(capsys: pytest.CaptureFixture[str]) -> None:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    try:
        server_module.configure_logging("INFO")
        logging.getLogger("pvsld.mcp").info("audit line")
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
    captured = capsys.readouterr()
    assert "audit line" in captured.err
    assert captured.out == ""


def test_the_preview_budget_can_be_lowered_without_touching_the_code(
    sandbox: OutputSandbox,
) -> None:
    small = create_server(sandbox, max_preview_bytes=30_000)
    result = call(small, GENERATE, {"spec": example_spec()})
    (image,) = images_of(result)
    assert len(base64.b64decode(image.data)) <= 30_000
    assert estimated_tokens(result) < 15_000


def test_a_png_that_cannot_be_saved_does_not_fail_the_drawing(
    server: Any, sandbox: OutputSandbox, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = OutputSandbox.publish

    def publish(self: OutputSandbox, staged: Path, target: Path) -> None:
        if target.suffix == ".png":
            raise server_module.SandboxError("cannot write PV-2026-0001.png: file in use.")
        original(self, staged, target)

    monkeypatch.setattr(OutputSandbox, "publish", publish)
    result = call(server, GENERATE, {"spec": example_spec()})
    assert not result.is_error
    assert len(images_of(result)) == 1
    assert result.structured_content is not None
    assert "png_path" not in result.structured_content
    assert "was not saved" in result.structured_content["preview"]
    assert (sandbox.root / "PV-2026-0001.dxf").is_file()
