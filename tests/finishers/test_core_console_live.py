"""Stage 2.4 on the licensed workstation: the real ``accoreconsole.exe`` (marker ``autocad``).

Run with ``pytest tests/finishers --run-autocad`` on Windows with a licensed AutoCAD 2027. Every
file is written under ``out/test-autocad`` (git-ignored); the owner's drawings and AutoCAD profile
are never used, because each run is ``/isolate``d into its own output folder.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pytest

from pvsld.finishers.core_console import FinishOptions, find_accoreconsole, finish
from s1_helpers import GOLDEN_DIR

pytestmark = pytest.mark.autocad

ROOT = Path(__file__).resolve().parents[2]
GOLDEN = GOLDEN_DIR / "residential_7p7kwp.dxf"
LIMIT_S = 15.0


@pytest.fixture
def live_dir(request: pytest.FixtureRequest) -> Path:
    folder = ROOT / "out" / "test-autocad" / re.sub(r"\W+", "_", request.node.name)
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)
    if find_accoreconsole() is None:
        pytest.fail("accoreconsole.exe not found: install AutoCAD 2027 or set PVSLD_ACCORECONSOLE")
    return folder


def _sheet(folder: Path, source: Path = GOLDEN) -> Path:
    target = folder / "sld.dxf"
    shutil.copyfile(source, target)
    return target


def _viewport_layer_zero(source: Path, target: Path) -> None:
    """The S1 sheet with its overall paper-space viewport on layer 0, as AutoCAD's AUDIT wants."""
    data = source.read_bytes()
    old = b"VIEWPORT\n  5\n123\n330\n1B\n100\nAcDbEntity\n 67\n1\n  8\nG-ANNO-NPLT\n"
    assert data.count(old) == 1
    target.write_bytes(data.replace(old, old.replace(b"G-ANNO-NPLT", b"0")))


def test_golden_dxf_becomes_dwg_2018_and_pdf_within_15_s(live_dir: Path) -> None:
    result = finish(_sheet(live_dir), options=FinishOptions(timeout_s=120))
    assert result.duration_s is not None
    assert result.duration_s <= LIMIT_S
    assert result.dwg is not None
    assert result.dwg.version == "AC1032"
    assert result.dwg.trusted
    assert result.pdf is not None
    assert result.pdf.pages == 1
    assert result.log.step("end") is not None
    # The S1 golden keeps its overall paper-space viewport off layer 0: AutoCAD's AUDIT reports it
    # twice (pass 1 and pass 2). Only that problem may remain until S1 moves the viewport back.
    assert result.audit is not None
    assert result.audit.errors_found in (0, 2)
    assert [p for p in result.problems if not p.startswith("AUDIT found 2 errors")] == []


def test_viewport_on_layer_zero_audits_clean(live_dir: Path) -> None:
    sheet = live_dir / "sld.dxf"
    _viewport_layer_zero(GOLDEN, sheet)
    result = finish(sheet, options=FinishOptions(timeout_s=120))
    assert result.ok, result.problems
    assert result.audit is not None
    assert (result.audit.errors_found, result.audit.errors_fixed) == (0, 0)


def test_produced_dwg_reopens_and_audits_clean(live_dir: Path) -> None:
    sheet = live_dir / "sld.dxf"
    _viewport_layer_zero(GOLDEN, sheet)
    assert finish(sheet, options=FinishOptions(pdf=False, timeout_s=120)).ok
    reopen = live_dir / "reopen"
    reopen.mkdir()
    dwg = reopen / "sld.dwg"
    shutil.copyfile(live_dir / "sld.dwg", dwg)
    result = finish(dwg, options=FinishOptions(dwg=False, pdf=False, timeout_s=120))
    assert result.ok, result.problems
    assert result.log.checks.get("dwgname") == "sld.dwg"


def test_invalid_input_is_reported(live_dir: Path) -> None:
    broken = live_dir / "broken.dxf"
    broken.write_text("0\nSECTION\n2\nHEADER\nthis is not a DXF\n", encoding="ascii")
    result = finish(broken, options=FinishOptions(timeout_s=120))
    assert not result.ok
    assert any(p.startswith("not produced:") for p in result.problems)


def test_timeout_stops_the_process_and_is_reported(live_dir: Path) -> None:
    result = finish(_sheet(live_dir), options=FinishOptions(timeout_s=1.0))
    assert not result.ok
    assert result.process is not None
    assert result.process.timed_out
    assert any("did not finish within 1 s" in p for p in result.problems)


def test_missing_plotter_is_reported(live_dir: Path) -> None:
    result = finish(_sheet(live_dir), options=FinishOptions(plotter="NoSuch.pc3", timeout_s=120))
    assert not result.ok
    assert f"not produced: {result.paths.pdf}" in result.problems
