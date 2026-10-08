"""The symbol library as DWG 2018 (Stage 4.4): the committed file and the export plumbing.

The export itself needs a licensed AutoCAD; here the Core Console run is replaced by a fake that
returns the committed DWG, and the committed DWG is checked against the committed DXF.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from pvsld.backends.base import sha256_hex
from pvsld.cli import main
from pvsld.finishers.core_console import FinisherError
from pvsld.symbols.cfe import dwg as library_dwg
from pvsld.symbols.cfe.dwg import (
    LibraryDwgError,
    check_dwg,
    check_dwg_file,
    export_dwg,
    manifest_path,
)
from pvsld.symbols.cfe.model import LIBRARY_VERSION
from s1_helpers import ROOT

DXF = ROOT / "symbols" / "pvsld-symbols-cfe.dxf"
DWG = ROOT / "symbols" / "pvsld-symbols.dwg"


def test_the_committed_dwg_is_a_trusted_dwg_2018_exported_from_the_committed_dxf() -> None:
    assert check_dwg(DXF, DWG) == []
    manifest = json.loads(manifest_path(DWG).read_text(encoding="utf-8"))
    assert manifest == {
        "library_version": LIBRARY_VERSION,
        "dxf_sha256": sha256_hex(DXF.read_bytes()),
        "dwg_release": "AC1032",
    }


def test_the_cli_check_passes_on_the_committed_files(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(ROOT)
    assert main(["symbols", "dwg", "--check"]) == 0
    assert "matches" in capsys.readouterr().out


@pytest.fixture
def copies(tmp_path: Path) -> tuple[Path, Path]:
    dxf, dwg = tmp_path / "lib.dxf", tmp_path / "lib.dwg"
    shutil.copyfile(DXF, dxf)
    shutil.copyfile(DWG, dwg)
    shutil.copyfile(manifest_path(DWG), manifest_path(dwg))
    return dxf, dwg


def test_a_changed_dxf_makes_the_dwg_stale(copies: tuple[Path, Path]) -> None:
    dxf, dwg = copies
    assert check_dwg(dxf, dwg) == []
    dxf.write_bytes(dxf.read_bytes() + b"\n")
    assert any("stale" in p for p in check_dwg(dxf, dwg))


def test_another_library_version_and_a_missing_manifest_are_reported(
    copies: tuple[Path, Path],
) -> None:
    dxf, dwg = copies
    manifest = manifest_path(dwg)
    data = json.loads(manifest.read_text(encoding="utf-8"))
    manifest.write_text(json.dumps({**data, "library_version": "0.0.1"}), encoding="utf-8")
    assert any("0.0.1" in p for p in check_dwg(dxf, dwg))
    manifest.unlink()
    assert any("missing" in p for p in check_dwg(dxf, dwg))


def test_a_file_that_is_not_an_autocad_dwg_2018_is_refused(tmp_path: Path) -> None:
    assert "missing" in check_dwg_file(tmp_path / "none.dwg")[0]
    fake = tmp_path / "fake.dwg"
    fake.write_bytes(b"AC1027" + b"\0" * 64)
    problems = check_dwg_file(fake)
    assert any("AC1027" in p for p in problems)
    assert any("TrustedDWG" in p for p in problems)


def _fake_finish(audit: tuple[int, int] = (0, 0), ok: bool = True) -> Any:
    def fake(source: Path, out_dir: Path, *, options: Any) -> Any:
        assert source.name == "lib.dxf"  # the DWG takes the stem of the opened file
        assert options.pdf is False
        target = out_dir / f"{source.stem}.dwg"
        shutil.copyfile(DWG, target)
        return SimpleNamespace(
            ok=ok,
            audit=SimpleNamespace(errors_found=audit[0], errors_fixed=audit[1]),
            problems=() if ok else ("Core Console exited with 1",),
            paths=SimpleNamespace(dwg=target),
        )

    return fake


def test_export_copies_the_dwg_and_records_the_dxf_it_came_from(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(library_dwg, "finish", _fake_finish())
    target = tmp_path / "out" / "lib.dwg"
    shutil.copyfile(DXF, tmp_path / "lib.dxf")
    export = export_dwg(tmp_path / "lib.dxf", target)
    assert export.audit == (0, 0)
    assert target.read_bytes() == DWG.read_bytes()
    assert check_dwg(tmp_path / "lib.dxf", target) == []


@pytest.mark.parametrize(
    ("fake", "message"),
    [
        (_fake_finish(audit=(2, 0)), "AUDIT found 2 errors"),
        (_fake_finish(ok=False), "exited with 1"),
    ],
)
def test_export_refuses_an_audit_error_or_a_failed_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: Any, message: str
) -> None:
    monkeypatch.setattr(library_dwg, "finish", fake)
    shutil.copyfile(DXF, tmp_path / "lib.dxf")
    with pytest.raises(LibraryDwgError, match=message):
        export_dwg(tmp_path / "lib.dxf", tmp_path / "lib.dwg")


def test_export_without_autocad_is_a_clear_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def missing(*_args: Any, **_kwargs: Any) -> Any:
        raise FinisherError("accoreconsole.exe not found")

    monkeypatch.setattr(library_dwg, "finish", missing)
    shutil.copyfile(DXF, tmp_path / "lib.dxf")
    with pytest.raises(LibraryDwgError, match="accoreconsole"):
        export_dwg(tmp_path / "lib.dxf", tmp_path / "lib.dwg")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "symbols").mkdir()
    shutil.copyfile(DXF, tmp_path / "symbols" / "pvsld-symbols-cfe.dxf")
    assert main(["symbols", "dwg"]) == 1
    assert "accoreconsole" in capsys.readouterr().err
