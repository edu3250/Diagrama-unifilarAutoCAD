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
    # The overall paper-space viewport is on layer 0, so AutoCAD's AUDIT is clean (S1 fix).
    assert result.audit is not None
    assert (result.audit.errors_found, result.audit.errors_fixed) == (0, 0)
    assert result.ok, result.problems


def test_produced_dwg_reopens_and_audits_clean(live_dir: Path) -> None:
    sheet = _sheet(live_dir)
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
    # The rejected device name puts the script out of step; Core Console then waits for input
    # for ever, so only the timeout ends the run.
    options = FinishOptions(plotter="NoSuch.pc3", timeout_s=20)
    result = finish(_sheet(live_dir), options=options)
    assert not result.ok
    assert result.process is not None
    assert result.process.timed_out
    assert "console: <NoSuch.pc3> no encontrado." in result.problems or any(
        "NoSuch.pc3> not found" in p for p in result.problems
    )
    assert f"not produced: {result.paths.pdf}" in result.problems
