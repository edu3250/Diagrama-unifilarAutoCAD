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

from pvsld.mcp.prompts import PROMPTS_ENV
from pvsld.mcp.sandbox import OutputSandbox
from pvsld.mcp.server import RECORD_EXAMPLES_URI, create_server
from sizing_helpers import FIXTURE_RECORDS
from test_mcp_server import run_client

ROOT = Path(__file__).resolve().parents[1]
MARKETPLACE = ROOT / ".claude-plugin" / "marketplace.json"
PLUGIN = ROOT / "plugins" / "pv-unifilar"
SKILLS = ("diagrama", "pro", "catalogo")
TOOL_PREFIX = "mcp__plugin_pv-unifilar_pvsld__"
REPOSITORY = "git+https://github.com/edu3250/PvUnifilar"


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
    assert server["env"][PROMPTS_ENV] == "off"  # Claude Code shows the skills


def test_the_portable_manifest_says_what_the_claude_one_says() -> None:
    """Agent Plugins 1.0 (root ``plugin.json`` and ``mcp.json``) is what Copilot CLI and Codex
    read; it lives beside Claude Code's files and must describe the same plugin."""
    claude = _json(PLUGIN / ".claude-plugin" / "plugin.json")
    portable = _json(PLUGIN / "plugin.json")
    assert portable.pop("$schema") == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert portable == {key: claude[key] for key in portable}
    assert {"name", "version", "description", "license"} <= set(portable)

    ours = _json(PLUGIN / ".mcp.json")["mcpServers"]["pvsld"]
    servers = _json(PLUGIN / "mcp.json")
    assert servers["$schema"] == "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
    (server,) = servers["mcpServers"].values()
    assert (server["type"], server["command"], server["args"]) == ("stdio", "uvx", ours["args"])
    # No client but Claude Code fills in ${user_config...}; the skills are shown, so no prompts.
    assert server["env"] == {"PYTHONUTF8": "1", PROMPTS_ENV: "off"}


def test_the_antigravity_file_names_the_same_server() -> None:
    """Antigravity CLI (Google's successor of Gemini CLI for personal accounts) installs this
    folder by its root ``plugin.json`` but reads the servers from ``mcp_config.json``: without
    it, ``agy plugin validate`` reports "mcpServers: skipped (not found)" (Stage 3.7)."""
    portable = _json(PLUGIN / "mcp.json")["mcpServers"]["pvsld"]
    (server,) = _json(PLUGIN / "mcp_config.json")["mcpServers"].values()
    assert server == {key: portable[key] for key in ("command", "args", "env")}


def test_the_gemini_extension_runs_the_same_server_with_its_prompts() -> None:
    """Gemini CLI installs an extension from the root of a repository, where there are no
    skills: the server's prompts are its commands, so they must stay on."""
    claude = _json(PLUGIN / ".claude-plugin" / "plugin.json")
    ours = _json(PLUGIN / ".mcp.json")["mcpServers"]["pvsld"]
    extension = _json(ROOT / "gemini-extension.json")
    assert (extension["name"], extension["version"]) == (claude["name"], claude["version"])
    (server,) = extension["mcpServers"].values()
    assert (server["command"], server["args"]) == ("uvx", ours["args"])
    assert PROMPTS_ENV not in server["env"]
    context = ROOT / extension["contextFileName"]
    assert "write a script that draws" in context.read_text(encoding="utf-8")


USER_DOCS = (PLUGIN / "README.md", ROOT / "README.md", ROOT / "docs" / "guia-de-usuario.md")


@pytest.mark.parametrize("document", USER_DOCS, ids=lambda path: path.name)
def test_the_user_documents_name_the_tag_of_this_version(document: Path) -> None:
    """A release changes the version in one go: no document may keep the old tag."""
    version = _json(PLUGIN / ".claude-plugin" / "plugin.json")["version"]
    text = document.read_text(encoding="utf-8")
    assert f"uvx --from {REPOSITORY}@v{version} pvsld-mcp --version" in text
    tags = set(re.findall(re.escape(REPOSITORY) + r"@(v[0-9][\w.]*)", text))
    assert tags == {f"v{version}"}


@pytest.mark.parametrize("document", USER_DOCS, ids=lambda path: path.name)
def test_the_user_documents_install_from_the_default_branch(document: Path) -> None:
    """`develop` is the default branch (owner, 2026-10-10): a pinned branch would outlive it."""
    text = document.read_text(encoding="utf-8")
    assert "edu3250/PvUnifilar@" not in text.replace(REPOSITORY + "@", "")
    assert "pv-unifilar@pvsld" in text


@pytest.mark.parametrize(
    "path",
    [
        *USER_DOCS,
        PLUGIN / ".mcp.json",
        PLUGIN / ".claude-plugin" / "plugin.json",
        PLUGIN / "mcp.json",
        PLUGIN / "mcp_config.json",
        PLUGIN / "plugin.json",
        ROOT / "gemini-extension.json",
        MARKETPLACE,
        ROOT / "pyproject.toml",
    ],
    ids=lambda path: path.name,
)
def test_what_a_user_reads_or_runs_names_the_repository_as_it_is_now(path: Path) -> None:
    """The repository was renamed PvUnifilar on 2026-10-12. GitHub redirects the old address only
    while nobody reuses that name, so nothing current may depend on it."""
    assert "Diagrama-unifilar" + "AutoCAD" not in path.read_text(encoding="utf-8")


@pytest.mark.parametrize("name", SKILLS)
def test_each_skill_has_a_spanish_description_and_a_hint(name: str) -> None:
    front, body = _skill(name)
    assert 50 < len(front["description"]) <= 1024  # the limit of the Agent Skills format
    assert front["argument-hint"]
    assert "Spanish" in body  # the skill tells the model to answer in Spanish


@pytest.mark.parametrize("name", SKILLS)
def test_each_skill_is_a_portable_agent_skill(name: str) -> None:
    """Gemini CLI lists no skill without ``name`` (it must be the folder's), and only Claude Code
    fills in ``$ARGUMENTS``: elsewhere the model would read the placeholder itself."""
    front, body = _skill(name)
    assert front["name"] == name
    assert "$ARGUMENTS" not in body
    assert "of this plugin" not in body  # the same text is served as an MCP prompt


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


@pytest.mark.parametrize("name", SKILLS)
def test_each_skill_says_what_to_do_when_the_server_is_not_connected(name: str) -> None:
    """The first start can outlast Claude Code's 30 s wait (31.6 s measured with an empty uv
    cache, Stage 3.6.5): the skill still loads, so it must send the user to /mcp, not improvise."""
    _, body = _skill(name)
    section = body[body.index("## If the pvsld tools are not available") :]
    assert "/mcp" in section
    assert "uv --version" in section
    assert "Do not design, calculate or draw by other means" in section


def test_the_catalogue_skill_reads_the_examples_resource() -> None:
    _, body = _skill("catalogo")
    assert RECORD_EXAMPLES_URI in body
