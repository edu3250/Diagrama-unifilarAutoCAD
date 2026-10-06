"""``pyproject.toml`` parses and carries the Stage 2.0 contract."""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path
from typing import Any

import pytest

PYPROJECT = Path(__file__).resolve().parents[1] / "pyproject.toml"


def _requirement_name(requirement: str) -> str:
    return re.split(r"[<>=!~;\[\s]", requirement, maxsplit=1)[0].lower()


@pytest.fixture(scope="module")
def pyproject() -> dict[str, Any]:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def test_build_backend_is_hatchling(pyproject: dict[str, Any]) -> None:
    assert pyproject["build-system"]["build-backend"] == "hatchling.build"


def test_project_identity(pyproject: dict[str, Any]) -> None:
    project = pyproject["project"]
    assert project["name"] == "pvsld"
    assert project["requires-python"] == ">=3.11"
    assert project["license"] == "MIT"


def test_runtime_dependencies(pyproject: dict[str, Any]) -> None:
    names = {_requirement_name(dep) for dep in pyproject["project"]["dependencies"]}
    assert names == {"ezdxf", "matplotlib", "mcp", "pillow", "pydantic", "pyyaml"}


def test_dev_extra_carries_the_toolchain(pyproject: dict[str, Any]) -> None:
    extra = pyproject["project"]["optional-dependencies"]["dev"]
    assert {_requirement_name(dep) for dep in extra} == {"pytest", "pytest-cov", "ruff"}


def test_autocad_extra_is_windows_only(pyproject: dict[str, Any]) -> None:
    (requirement,) = pyproject["project"]["optional-dependencies"]["autocad"]
    assert _requirement_name(requirement) == "pywin32"
    assert "sys_platform == 'win32'" in requirement


def test_console_script_target_is_importable(pyproject: dict[str, Any]) -> None:
    target = pyproject["project"]["scripts"]["pvsld"]
    module_name, _, attribute = target.partition(":")
    assert module_name == "pvsld.cli"
    assert callable(getattr(importlib.import_module(module_name), attribute))


def test_pytest_is_strict_and_declares_the_autocad_marker(pyproject: dict[str, Any]) -> None:
    options = pyproject["tool"]["pytest"]["ini_options"]
    assert "--strict-markers" in options["addopts"]
    assert any(marker.startswith("autocad:") for marker in options["markers"])


def test_coverage_floor_is_at_least_sixty_percent(pyproject: dict[str, Any]) -> None:
    coverage = pyproject["tool"]["coverage"]
    assert coverage["run"]["source"] == ["pvsld"]
    assert coverage["report"]["fail_under"] >= 60
