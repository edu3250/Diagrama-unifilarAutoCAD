"""Stage 3.7: the plugin's skills are also MCP prompts, for the clients that do not load skills."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from pvsld.mcp.prompts import (
    NOT_CONNECTED_HEADING,
    PROMPTS_ENV,
    WORKFLOWS,
    load_workflow,
    prompts_enabled,
)
from pvsld.mcp.sandbox import OutputSandbox
from pvsld.mcp.server import create_server
from sizing_helpers import FIXTURE_RECORDS
from test_mcp_server import run_client

SKILLS = Path(__file__).resolve().parents[1] / "plugins" / "pv-unifilar" / "skills"


@pytest.fixture
def server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.delenv(PROMPTS_ENV, raising=False)
    return create_server(OutputSandbox.at(tmp_path / "out"), catalogue_dir=FIXTURE_RECORDS)


def test_the_server_offers_one_prompt_per_skill(server: Any) -> None:
    prompts = run_client(server, lambda client: client.list_prompts()).prompts
    assert [prompt.name for prompt in prompts] == list(WORKFLOWS)
    for prompt in prompts:
        (argument,) = prompt.arguments or []
        assert argument.required is False  # a client may run the command with nothing after it
        assert prompt.description == load_workflow(prompt.name).description
        assert prompt.title
        assert prompt.title.startswith("PvUnifilar")


@pytest.mark.parametrize("name", WORKFLOWS)
def test_a_prompt_is_the_skill_without_what_only_a_skill_needs(name: str) -> None:
    """One text for both: a prompt that drifted from its skill would teach two workflows."""
    skill = (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")
    workflow = load_workflow(name)
    assert workflow.instructions in skill
    assert workflow.instructions.startswith("# PvUnifilar")
    assert "description:" not in workflow.instructions  # no front matter
    # What to do when the server is down is for the skill: a prompt comes from the server.
    assert NOT_CONNECTED_HEADING in skill
    assert NOT_CONNECTED_HEADING not in workflow.instructions


def test_what_the_user_wrote_follows_the_instructions(server: Any) -> None:
    def text(arguments: dict[str, str]) -> str:
        result = run_client(server, lambda client: client.get_prompt("diagrama", arguments))
        (message,) = result.messages
        assert message.role == "user"
        return str(message.content.text)

    plain = text({})
    asked = text({"peticion": "  8 paneles Jinko de 475 W "})
    assert plain == load_workflow("diagrama").instructions
    assert asked == plain + "\n\nRequest: 8 paneles Jinko de 475 W\n"


@pytest.mark.parametrize("value", ["off", "OFF", "0", "false", " no "])
def test_the_prompts_can_be_left_out(
    value: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Where the plugin already shows the skills, every command would appear twice."""
    monkeypatch.setenv(PROMPTS_ENV, value)
    quiet = create_server(OutputSandbox.at(tmp_path / "out"), catalogue_dir=FIXTURE_RECORDS)
    assert run_client(quiet, lambda client: client.list_prompts()).prompts == []
    assert len(run_client(quiet, lambda client: client.list_tools()).tools) == 9


@pytest.mark.parametrize("value", ["", "on", "1", "si"])
def test_the_prompts_are_on_unless_turned_off(value: str) -> None:
    assert prompts_enabled({PROMPTS_ENV: value})
    assert prompts_enabled({})
