"""Stage 3.6.4b: the Claude Code plugin PvUnifilar and its marketplace are consistent.

``claude plugin validate --strict`` checks the formats (CI job ``claude-plugin``); these tests check
what it cannot know: the plugin's version matches the package, the server runs from the matching
release tag, and every tool the skills pre-approve or name is one the server really has.
"""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest
import yaml

from pvsld.mcp.sandbox import OutputSandbox
from pvsld.mcp.server import RECORD_EXAMPLES_URI, create_server
from sizing_helpers import FIXTURE_RECORDS
from test_mcp_server import run_client

ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN = ROOT / "plugins" / "pv-unifilar"
SKILLS = ("diagrama", "pro", "catalogo")
TOOL_PREFIX = "mcp__plugin_pv-unifilar_pvsld__"
REPOSITORY = "git+https://github.com/edu3250/Diagrama-unifilarAutoCAD"


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _skill(name: str) -> tuple[dict[str, Any], str]:
    text = (PLUGIN / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
    match = re.match(r"---\n(.*?)\n---\n(.*)", text, flags=re.DOTALL)
    assert match, f"{name}: SKILL.md must start with YAML frontmatter"
    return yaml.safe_load(match.group(1)), match.group(2)


@pytest.fixture(scope="module")
def server_tools(tmp_path_factory: pytest.TempPathFactory) -> set[str]:
    server = create_server(
        OutputSandbox.at(tmp_path_factory.mktemp("out")), catalogue_dir=FIXTURE_RECORDS
    )
    return {tool.name for tool in run_client(server, lambda client: client.list_tools()).tools}


def test_the_marketplace_lists_the_plugin_folder() -> None:
    market = _json(MARKETPLACE)
    assert market["name"] == "pvsld"
    (entry,) = market["plugins"]
    assert entry["name"] == "pv-unifilar"
    assert (ROOT / entry["source"]).resolve() == PLUGIN.resolve()


def test_the_plugin_names_and_version_match_the_package() -> None:
    manifest = _json(PLUGIN / ".claude-plugin" / "plugin.json")
    with (ROOT / "pyproject.toml").open("rb") as handle:
        version = tomllib.load(handle)["project"]["version"]
    assert manifest["name"] == "pv-unifilar"
    assert manifest["displayName"] == "PvUnifilar"
    assert manifest["version"] == version


def test_the_server_runs_from_the_release_tag_of_this_version() -> None:
    server = _json(PLUGIN / ".mcp.json")["mcpServers"]["pvsld"]
    version = _json(PLUGIN / ".claude-plugin" / "plugin.json")["version"]
    assert server["command"] == "uvx"
    assert server["args"] == ["--from", f"{REPOSITORY}@v{version}", "pvsld-mcp"]
    assert server["env"]["PVSLD_OUTPUT_DIR"] == "${user_config.output_dir}"


def test_the_readme_warm_up_command_uses_the_same_tag() -> None:
    version = _json(PLUGIN / ".claude-plugin" / "plugin.json")["version"]
    readme = (PLUGIN / "README.md").read_text(encoding="utf-8")
    assert f"uvx --from {REPOSITORY}@v{version} pvsld-mcp --version" in readme


@pytest.mark.parametrize("name", SKILLS)
def test_each_skill_has_a_spanish_description_and_a_hint(name: str) -> None:
    front, body = _skill(name)
    assert 50 < len(front["description"]) < 1536
    assert front["argument-hint"]
    assert "$ARGUMENTS" in body
    assert "Spanish" in body  # the skill tells Claude to answer in Spanish


@pytest.mark.parametrize("name", SKILLS)
def test_pre_approved_tools_exist_and_are_used(name: str, server_tools: set[str]) -> None:
    front, body = _skill(name)
    allowed = front["allowed-tools"].split()
    assert allowed
    for tool in allowed:
        assert tool.startswith(TOOL_PREFIX), tool
        bare = tool.removeprefix(TOOL_PREFIX)
        assert bare in server_tools, bare
        assert f"`{bare}`" in body, f"{name} pre-approves {bare} but never names it"


@pytest.mark.parametrize("name", SKILLS)
def test_every_tool_a_skill_calls_exists(name: str, server_tools: set[str]) -> None:
    """A typo in "Call `x`" would send Claude after a tool that is not there."""
    _, body = _skill(name)
    called = set(re.findall(r"[Cc]all `([a-z_]+)`", body))
    assert called
    assert called <= server_tools, called - server_tools


def test_the_catalogue_skill_reads_the_examples_resource() -> None:
    _, body = _skill("catalogo")
    assert RECORD_EXAMPLES_URI in body
