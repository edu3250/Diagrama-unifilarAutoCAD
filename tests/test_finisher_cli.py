"""``pvsld finish`` with a fake Core Console (no AutoCAD needed)."""

from __future__ import annotations

import functools
import json
import shutil
from pathlib import Path

import pytest

from pvsld import cli
from pvsld.finishers import core_console
from pvsld.finishers.fake import FakeCoreConsole
from s1_helpers import GOLDEN_DIR


@pytest.fixture
def exe(tmp_path: Path) -> Path:
    path = tmp_path / "accoreconsole.exe"
    path.write_bytes(b"MZ")
    return path


@pytest.fixture
def sheet(tmp_path: Path) -> Path:
    path = tmp_path / "sld.dxf"
    shutil.copyfile(GOLDEN_DIR / "residential_7p7kwp.dxf", path)
    return path


def _use_fake(monkeypatch: pytest.MonkeyPatch, fake: FakeCoreConsole) -> None:
    monkeypatch.setattr(cli, "finish", functools.partial(core_console.finish, runner=fake))


def test_finish_reports_the_outputs(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    sheet: Path,
    exe: Path,
    tmp_path: Path,
) -> None:
    fake = FakeCoreConsole()
    _use_fake(monkeypatch, fake)
    out_dir = tmp_path / "finished"
    code = cli.main(["finish", str(sheet), "-d", str(out_dir), "--accoreconsole", str(exe)])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.out.startswith("OK: Core Console finished sld.dxf in 4.2 s")
    assert "AC1032, DWG 2018" in captured.out
    assert "TrustedDWG text present" in captured.out
    assert "1 page(s); 420 x 297 mm" in captured.out
    assert "audit: 0 errors found, 0 fixed" in captured.out
    assert "steps (ms): audit 250, saveas 250, plot 250, script_end 250" in captured.out
    assert "outside_script 3200" in captured.out
    assert (out_dir / "sld.dwg").is_file()
    assert "/isolate" in fake.calls[0]


def test_finish_json_and_options(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    sheet: Path,
    exe: Path,
) -> None:
    fake = FakeCoreConsole()
    _use_fake(monkeypatch, fake)
    argv = ["finish", str(sheet), "--accoreconsole", str(exe), "--no-pdf", "--no-isolate"]
    code = cli.main([*argv, "--audit-fix", "--timeout", "30", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert code == 0
    assert data["ok"] is True
    assert data["pdf_path"] is None
    assert data["dwg"]["version"] == "AC1032"
    assert "/isolate" not in fake.calls[0]
    script = Path(data["script_path"]).read_bytes().decode("ascii").split("\r\n")
    assert script[script.index("_.AUDIT") + 1] == "_Y"


def test_finish_failure_goes_to_stderr_with_exit_code_1(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    sheet: Path,
    exe: Path,
) -> None:
    _use_fake(monkeypatch, FakeCoreConsole(silent=True))
    code = cli.main(["finish", str(sheet), "--accoreconsole", str(exe)])
    captured = capsys.readouterr()
    assert code == 1
    assert captured.out == ""
    assert captured.err.startswith("FAILED: Core Console finished sld.dxf")
    assert "audit: not found" in captured.err
    assert "problem: accoreconsole printed nothing" in captured.err


def test_finish_without_core_console_is_an_error(
    capsys: pytest.CaptureFixture[str], sheet: Path, tmp_path: Path
) -> None:
    code = cli.main(["finish", str(sheet), "--accoreconsole", str(tmp_path / "none.exe")])
    assert code == 1
    assert "accoreconsole.exe not found" in capsys.readouterr().err


def test_finish_refuses_to_overwrite_without_the_flag(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    sheet: Path,
    exe: Path,
) -> None:
    _use_fake(monkeypatch, FakeCoreConsole())
    argv = ["finish", str(sheet), "--accoreconsole", str(exe)]
    assert cli.main(argv) == 0
    capsys.readouterr()
    assert cli.main(argv) == 1
    assert "output exists" in capsys.readouterr().err
    assert cli.main([*argv, "--overwrite"]) == 0


def test_finish_help_lists_the_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        cli.main(["--help"])
    assert excinfo.value.code == 0
    assert "finish" in capsys.readouterr().out
