"""Stage 3.6.4: bundled data resolves inside the installed package, else in the repository."""

from __future__ import annotations

from pathlib import Path

import pytest

from pvsld import resources
from pvsld.resources import REPOSITORY, data_path

DATA = (
    "datasheets/records",
    "symbols/pvsld-symbols.dxf",
    "sheet_templates/a3_plantilla_v1.dxf",
    "examples/residential_7p7kwp.yaml",
)


@pytest.mark.parametrize("relative", DATA)
def test_a_development_checkout_reads_the_repository(relative: str) -> None:
    assert data_path(relative) == REPOSITORY / relative
    assert data_path(relative).exists()


def test_the_packaged_copy_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    packaged = tmp_path / "_data"
    (packaged / "symbols").mkdir(parents=True)
    (packaged / "symbols" / "pvsld-symbols.dxf").write_text("0\nEOF\n", encoding="utf-8")
    monkeypatch.setattr(resources, "PACKAGE_DATA", packaged)
    assert data_path("symbols/pvsld-symbols.dxf") == packaged / "symbols" / "pvsld-symbols.dxf"
    assert data_path("datasheets/records") == REPOSITORY / "datasheets" / "records"


def test_every_runtime_file_is_forced_into_the_wheel() -> None:
    """The force-include table of pyproject.toml lists each file data_path serves."""
    import tomllib

    with (REPOSITORY / "pyproject.toml").open("rb") as handle:
        table = tomllib.load(handle)["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert table == {relative: f"pvsld/_data/{relative}" for relative in DATA}
