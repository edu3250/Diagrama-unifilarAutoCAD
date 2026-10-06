"""The package imports, exposes a version and ships its typing marker."""

from __future__ import annotations

import importlib
import importlib.metadata
from importlib import resources

import pytest

import pvsld

SUBPACKAGES = ("core", "backends", "transports", "finishers")


def test_version_is_a_non_empty_string() -> None:
    assert isinstance(pvsld.__version__, str)
    assert pvsld.__version__


def test_version_matches_installed_metadata() -> None:
    assert pvsld.__version__ == importlib.metadata.version("pvsld")


def test_version_falls_back_when_package_metadata_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _missing(name: str) -> str:
        raise importlib.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(importlib.metadata, "version", _missing)
    try:
        assert importlib.reload(pvsld).__version__ == "0.0.0+unknown"
    finally:
        monkeypatch.undo()
        importlib.reload(pvsld)


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_subpackage_imports_and_documents_its_role(name: str) -> None:
    module = importlib.import_module(f"pvsld.{name}")
    assert module.__doc__ is not None
    assert module.__doc__.strip()


def test_package_ships_the_py_typed_marker() -> None:
    assert resources.files("pvsld").joinpath("py.typed").is_file()
