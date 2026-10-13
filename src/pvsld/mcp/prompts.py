"""The three PvUnifilar workflows as MCP prompts (Stage 3.7).

The plugin's skills (``plugins/pv-unifilar/skills``) tell the model how to run the quick mode, the
professional mode and the catalogue workflow. A skill only reaches the clients that load that
plugin; an MCP prompt reaches every client that connects to the server and shows prompts (Gemini
CLI and VS Code list them as slash commands). The prompts are those same ``SKILL.md`` files, read
from the wheel (``force-include`` in ``pyproject.toml``), so the two cannot drift apart.

``PVSLD_MCP_PROMPTS=off`` leaves them out: the plugin sets it where the client already shows the
skills, so the user does not see every command twice.
"""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from dataclasses import dataclass

from pvsld.resources import data_path

__all__ = ["PROMPTS_ENV", "WORKFLOWS", "Workflow", "load_workflow", "prompts_enabled"]

PROMPTS_ENV = "PVSLD_MCP_PROMPTS"
SKILLS_FOLDER = "plugins/pv-unifilar/skills"
WORKFLOWS = ("diagrama", "pro", "catalogo")
NOT_CONNECTED_HEADING = "## If the pvsld tools are not available"
"""What a skill says when the server is down; a prompt comes from the server, so it is cut."""

_FRONT_MATTER = re.compile(r"---\n(.*?)\n---\n(.*)", flags=re.DOTALL)
_DESCRIPTION = re.compile(r"^description: (.+)$", flags=re.MULTILINE)


@dataclass(frozen=True)
class Workflow:
    """One skill of the plugin: its name, its Spanish description and its instructions."""

    name: str
    description: str
    instructions: str

    def text(self, request: str = "") -> str:
        """The instructions, followed by what the user wrote with the command."""
        request = request.strip()
        return f"{self.instructions}\n\nRequest: {request}\n" if request else self.instructions


def load_workflow(name: str) -> Workflow:
    """Read ``SKILL.md`` of the skill ``name``.

    Raises:
        ValueError: the file has no front matter with a one-line description.
    """
    path = data_path(f"{SKILLS_FOLDER}/{name}/SKILL.md")
    whole = _FRONT_MATTER.match(path.read_text(encoding="utf-8"))
    described = _DESCRIPTION.search(whole.group(1)) if whole else None
    if whole is None or described is None:
        raise ValueError(f"{path} must start with front matter that has a description")
    body = whole.group(2).split(NOT_CONNECTED_HEADING)[0]
    return Workflow(name, described.group(1).strip(), body.strip())


def prompts_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """Whether the server offers the prompts: yes unless ``$PVSLD_MCP_PROMPTS`` is ``off``."""
    source = os.environ if environ is None else environ
    return source.get(PROMPTS_ENV, "").strip().lower() not in {"off", "0", "false", "no"}
