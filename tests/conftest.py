"""Shared pytest configuration.

Tests marked ``@pytest.mark.autocad`` drive a licensed local AutoCAD 2027 and can only run on
Windows. They are skipped, with a visible reason, unless ``--run-autocad`` is passed on Windows,
so hosted CI (Linux and Windows runners without AutoCAD) reports them as skipped, never failed.
"""

from __future__ import annotations

import sys

import pytest

# ``pytester`` runs pytest inside pytest; it is used to prove the skip mechanism end to end.
pytest_plugins = ["pytester"]


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--run-autocad",
        action="store_true",
        default=False,
        help="Run tests marked 'autocad' (need a licensed local AutoCAD 2027 on Windows).",
    )


def _platform() -> str:
    return sys.platform


def autocad_skip_reason(run_autocad: bool, platform: str) -> str | None:
    """Return why ``autocad`` tests must be skipped, or ``None`` when they may run."""
    if not run_autocad:
        return "needs a licensed local AutoCAD 2027: pass --run-autocad to run (Windows only)"
    if platform != "win32":
        return "--run-autocad was given, but AutoCAD tests only run on Windows"
    return None


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    reason = autocad_skip_reason(config.getoption("--run-autocad"), _platform())
    if reason is None:
        return
    skip_autocad = pytest.mark.skip(reason=reason)
    for item in items:
        if "autocad" in item.keywords:
            item.add_marker(skip_autocad)


@pytest.fixture(autouse=True)
def _isolated_local_catalogue(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point the local catalogue (Stage 3.6.3) at an empty folder, never the user's own."""
    monkeypatch.setenv("PVSLD_LOCAL_CATALOGUE_DIR", str(tmp_path_factory.mktemp("local_catalogue")))
