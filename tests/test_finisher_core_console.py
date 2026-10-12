"""Core Console finisher without AutoCAD: script, command line, process handling and assessment.

A run of the real ``accoreconsole.exe`` is in ``tests/finishers`` (marker ``autocad``). Here a fake
runner plays Core Console, and each knob breaks one thing to prove the finisher reports it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from pvsld.finishers import core_console as core_console_module
from pvsld.finishers.core_console import (
    ENV_ACCORECONSOLE,
    FinisherError,
    FinishOptions,
    FinishResult,
    build_command,
    build_script,
    find_accoreconsole,
    finish,
    plan_paths,
    run_process,
)
from pvsld.finishers.fake import FakeCoreConsole
from s1_helpers import GOLDEN_DIR

GOLDEN = GOLDEN_DIR / "residential_7p7kwp.dxf"


@pytest.fixture
def exe(tmp_path: Path) -> Path:
    """A stand-in executable path (the fake runner never starts it)."""
    path = tmp_path / "AutoCAD 2027" / "accoreconsole.exe"
    path.parent.mkdir()
    path.write_bytes(b"MZ")
    return path


@pytest.fixture
def sheet(tmp_path: Path) -> Path:
    path = tmp_path / "work" / "sld.dxf"
    path.parent.mkdir()
    shutil.copyfile(GOLDEN, path)
    return path


def _finish(
    sheet: Path, exe: Path, fake: FakeCoreConsole | None = None, **options: object
) -> FinishResult:
    return finish(
        sheet,
        options=FinishOptions(**options),  # type: ignore[arg-type]
        accoreconsole=exe,
        runner=fake or FakeCoreConsole(),
    )


# --- locating accoreconsole.exe ---------------------------------------------------------------


def test_explicit_path_wins_and_must_exist(exe: Path, tmp_path: Path) -> None:
    assert find_accoreconsole(exe, environ={}) == exe
    assert find_accoreconsole(tmp_path / "missing.exe", environ={}) is None


def test_environment_variable_is_used_next(exe: Path, tmp_path: Path) -> None:
    assert find_accoreconsole(environ={ENV_ACCORECONSOLE: str(exe)}) == exe
    missing = {ENV_ACCORECONSOLE: str(tmp_path / "nope.exe")}
    assert find_accoreconsole(environ=missing, program_dirs=[exe.parent]) is None


def test_newest_autocad_under_program_files_is_found(tmp_path: Path) -> None:
    autodesk = tmp_path / "Autodesk"
    for release in ("AutoCAD 2026", "AutoCAD 2027", "AutoCAD LT 2027"):
        (autodesk / release).mkdir(parents=True)
        (autodesk / release / "accoreconsole.exe").write_bytes(b"MZ")
    found = find_accoreconsole(environ={"ProgramW6432": str(tmp_path)})
    assert found == autodesk / "AutoCAD 2027" / "accoreconsole.exe"


def test_nothing_found_without_autodesk_folder(tmp_path: Path) -> None:
    assert find_accoreconsole(environ={"ProgramFiles": str(tmp_path)}) is None
    assert find_accoreconsole(environ={}, program_dirs=[tmp_path]) is None


# --- paths, script and command line -----------------------------------------------------------


def test_plan_paths_puts_everything_in_the_output_folder(tmp_path: Path) -> None:
    paths = plan_paths(tmp_path / "in" / "sld.dxf", tmp_path / "out")
    assert paths.dwg == (tmp_path / "out" / "sld.dwg").resolve()
    assert paths.pdf.name == "sld.pdf"
    assert paths.script.name == "sld.finish.scr"
    assert paths.log.name == "sld.accoreconsole.log"
    assert paths.isolate_dir.parent == paths.out_dir
    assert plan_paths(tmp_path / "sld.dxf").out_dir == tmp_path.resolve()


def test_script_runs_audit_saveas_plot_and_quit_in_order(tmp_path: Path) -> None:
    paths = plan_paths(tmp_path / "sld.dxf")
    script = build_script(paths, FinishOptions())
    assert script.endswith("\r\n")
    lines = script.split("\r\n")
    commands = [line for line in lines if line.startswith("_.")]
    assert commands == ["_.AUDIT", "_.SAVEAS", "_.-PLOT", "_.QUIT"]
    assert lines[lines.index("_.AUDIT") + 1] == "_N"
    assert lines[lines.index("_.SAVEAS") + 1 : lines.index("_.SAVEAS") + 3] == [
        "_2018",
        str(paths.dwg),
    ]
    plot = lines[lines.index("_.-PLOT") :][:8]
    assert plot == ["_.-PLOT", "_N", "A3", "", "DWG To PDF.pc3", str(paths.pdf), "_N", "_Y"]
    steps = [name for name in ("loaded", "audited", "saved", "plotted", "end") if name in script]
    assert steps == ["loaded", "audited", "saved", "plotted", "end"]
    assert script.index(":STEP:loaded:") < script.index("_.AUDIT") < script.index(":STEP:audited:")
    assert script.isascii()
    # Core Console lacks (layoutlist), and its DATE only advances in whole seconds.
    assert "(layoutlist)" not in script
    assert '(dictsearch (namedobjdict) "ACAD_LAYOUT")' in script
    assert '(getvar "MILLISECS")' in script
    assert '"DATE"' not in script


def test_script_without_dwg_and_pdf_only_audits(tmp_path: Path) -> None:
    script = build_script(plan_paths(tmp_path / "sld.dwg"), FinishOptions(dwg=False, pdf=False))
    assert "_.SAVEAS" not in script
    assert "_.-PLOT" not in script
    assert "_.AUDIT" in script
    assert ":STEP:end:" in script


def test_script_with_audit_fix_answers_yes(tmp_path: Path) -> None:
    lines = build_script(plan_paths(tmp_path / "a.dxf"), FinishOptions(audit_fix=True)).split(
        "\r\n"
    )
    assert lines[lines.index("_.AUDIT") + 1] == "_Y"


def test_script_with_an_explicit_paper_uses_the_detailed_plot(tmp_path: Path) -> None:
    paths = plan_paths(tmp_path / "sld.dxf")
    options = FinishOptions(paper="ISO full bleed A3 (420.00 x 297.00 MM)")
    lines = build_script(paths, options).split("\r\n")
    start = lines.index("_.-PLOT")
    assert lines[start + 1 : start + 5] == [
        "_Y",
        "A3",
        "DWG To PDF.pc3",
        "ISO full bleed A3 (420.00 x 297.00 MM)",
    ]
    assert "monochrome.ctb" in lines
    assert lines[lines.index(str(paths.pdf)) + 1 : lines.index(str(paths.pdf)) + 3] == ["_N", "_Y"]


def test_dxfin_mode_imports_the_drawing_and_drops_the_i_switch(tmp_path: Path, exe: Path) -> None:
    paths = plan_paths(tmp_path / "sld.dxf")
    options = FinishOptions(open_mode="dxfin")
    lines = build_script(paths, options).split("\r\n")
    assert lines[:2] == ["_.DXFIN", str(paths.source)]
    assert "/i" not in build_command(exe, paths, options)


def test_paths_with_spaces_are_quoted(tmp_path: Path) -> None:
    paths = plan_paths(tmp_path / "with space" / "sld.dxf")
    lines = build_script(paths, FinishOptions()).split("\r\n")
    assert f'"{paths.dwg}"' in lines
    assert f'"{paths.pdf}"' in lines


def test_non_ascii_paths_are_refused(tmp_path: Path) -> None:
    with pytest.raises(FinisherError, match="cannot be written to a Core Console script"):
        build_script(plan_paths(tmp_path / "Diseño" / "sld.dxf"), FinishOptions())


@pytest.mark.parametrize("bad", ["Diseño", 'a"b', "two\nlines", ""])
def test_values_that_cannot_be_scripted_are_refused(tmp_path: Path, bad: str) -> None:
    with pytest.raises(FinisherError, match="layout"):
        build_script(plan_paths(tmp_path / "sld.dxf"), FinishOptions(layout=bad))
    with pytest.raises(FinisherError, match="plotter"):
        build_script(plan_paths(tmp_path / "sld.dxf"), FinishOptions(plotter=bad))


def test_command_line_has_drawing_script_and_isolation(tmp_path: Path, exe: Path) -> None:
    paths = plan_paths(tmp_path / "sld.dxf")
    command = build_command(exe, paths, FinishOptions())
    assert command == [
        str(exe),
        "/i",
        str(paths.source),
        "/s",
        str(paths.script),
        "/isolate",
        "pvsld",
        str(paths.isolate_dir),
    ]
    assert "/isolate" not in build_command(exe, paths, FinishOptions(isolate=False))


# --- a healthy run ----------------------------------------------------------------------------


def test_healthy_run_is_ok_and_reports_everything(sheet: Path, exe: Path) -> None:
    fake = FakeCoreConsole()
    result = _finish(sheet, exe, fake)
    assert result.ok, result.problems
    assert result.problems == ()
    assert result.paths.dwg.is_file()
    assert result.paths.pdf.is_file()
    assert result.audit is not None
    assert result.audit.errors_found == 0
    assert result.dwg is not None
    assert result.dwg.version == "AC1032"
    assert result.dwg.trusted
    assert result.pdf is not None
    assert result.pdf.pages == 1
    assert result.duration_s == 4.2
    assert result.step_ms == {
        "audit": 250,
        "saveas": 250,
        "plot": 250,
        "script_end": 250,
        "outside_script": 3200,
    }
    assert result.paths.isolate_dir.is_dir()
    assert result.paths.script.read_bytes().isascii()
    assert "PVSLD:STEP:end" in result.paths.log.read_text(encoding="utf-8")
    assert fake.calls[0][1:3] == ["/i", str(sheet.resolve())]


def test_to_dict_is_json_serializable(sheet: Path, exe: Path) -> None:
    data = _finish(sheet, exe).to_dict()
    text = json.dumps(data)
    assert data["ok"] is True
    assert data["dwg"]["version"] == "AC1032"
    assert data["dwg"]["trusted_dwg"] is True
    assert data["pdf"]["page_sizes_mm"] == [[420.0, 297.0]]
    assert data["audit"] == {"errors_found": 0, "errors_fixed": 0}
    assert "problems" in text


def test_audit_only_run_of_a_dwg(sheet: Path, exe: Path, tmp_path: Path) -> None:
    dwg = tmp_path / "work" / "copy.dwg"
    dwg.write_bytes(b"AC1032")
    result = _finish(dwg, exe, dwg=False, pdf=False)
    assert result.ok, result.problems
    assert result.dwg is None
    assert result.pdf is None
    assert result.to_dict()["dwg_path"] is None


# --- failures are reported, never silent ------------------------------------------------------


def test_silent_exit_without_licence_is_a_failure(sheet: Path, exe: Path) -> None:
    result = _finish(sheet, exe, FakeCoreConsole(silent=True))
    assert not result.ok
    joined = "\n".join(result.problems)
    assert "printed nothing" in joined
    assert "licence" in joined
    assert "stopped before step(s) loaded, audited, saved, plotted, end" in joined
    assert f"not produced: {result.paths.dwg}" in joined
    assert f"not produced: {result.paths.pdf}" in joined


def test_non_zero_exit_code_is_a_failure(sheet: Path, exe: Path) -> None:
    result = _finish(sheet, exe, FakeCoreConsole(exit_code=-1073741819))
    assert not result.ok
    assert "accoreconsole exited with code -1073741819" in result.problems


def test_timeout_is_a_failure_that_names_the_stopped_process(sheet: Path, exe: Path) -> None:
    result = _finish(sheet, exe, FakeCoreConsole(timed_out=True, steps=("loaded",)))
    assert not result.ok
    assert any("did not finish within 60 s" in p and "pid 4242" in p for p in result.problems)
    assert result.to_dict()["timed_out"] is True


def test_missing_pdf_alone_is_a_failure(sheet: Path, exe: Path) -> None:
    result = _finish(sheet, exe, FakeCoreConsole(write_pdf=False))
    assert not result.ok
    assert result.problems == (f"not produced: {result.paths.pdf}",)
    assert result.dwg is not None
    assert result.pdf is None


def test_wrong_dwg_version_is_a_failure(sheet: Path, exe: Path) -> None:
    result = _finish(sheet, exe, FakeCoreConsole(dwg_version=b"AC1027"))
    assert "DWG version is AC1027, expected AC1032 (DWG 2018)" in result.problems


def test_audit_errors_are_a_failure(sheet: Path, exe: Path) -> None:
    result = _finish(sheet, exe, FakeCoreConsole(audit_line="Total errors found 4 fixed 0"))
    assert not result.ok
    assert result.audit is not None
    assert result.audit.errors_found == 4
    assert any(p.startswith("AUDIT found 4 errors") for p in result.problems)


def test_missing_audit_summary_is_a_failure(sheet: Path, exe: Path) -> None:
    result = _finish(sheet, exe, FakeCoreConsole(audit_line=None))
    assert "the AUDIT summary was not found in the console log" in result.problems


def test_problem_phrase_in_the_log_is_a_failure(sheet: Path, exe: Path) -> None:
    fake = FakeCoreConsole(extra_lines=("Unknown command. Press F1 for help.",))
    result = _finish(sheet, exe, fake)
    assert result.problems == ("console: Unknown command. Press F1 for help.",)


def test_script_out_of_step_is_a_failure(sheet: Path, exe: Path) -> None:
    result = _finish(sheet, exe, FakeCoreConsole(steps=("loaded", "audited", "saved")))
    assert any("stopped before step(s) plotted, end" in p for p in result.problems)


def test_empty_drawing_and_missing_layout_are_failures(sheet: Path, exe: Path) -> None:
    result = _finish(sheet, exe, FakeCoreConsole(entities=0, layouts="Layout1|"))
    assert "the drawing loaded without entities (count 0)" in result.problems
    assert "layout 'A3' is not in the drawing" in result.problems


# --- refusals before any process starts -------------------------------------------------------


def test_missing_core_console_raises(sheet: Path, tmp_path: Path) -> None:
    with pytest.raises(FinisherError, match=r"accoreconsole\.exe not found"):
        finish(sheet, accoreconsole=tmp_path / "none.exe", runner=FakeCoreConsole())


def test_missing_or_unsupported_source_raises(exe: Path, tmp_path: Path) -> None:
    with pytest.raises(FinisherError, match="drawing not found"):
        _finish(tmp_path / "nope.dxf", exe)
    text = tmp_path / "notes.txt"
    text.write_text("x", encoding="utf-8")
    with pytest.raises(FinisherError, match=r"expected a \.dxf or \.dwg"):
        _finish(text, exe)


def test_dxfin_needs_a_dxf(exe: Path, tmp_path: Path) -> None:
    dwg = tmp_path / "a.dwg"
    dwg.write_bytes(b"AC1032")
    with pytest.raises(FinisherError, match="dxfin"):
        _finish(dwg, exe, open_mode="dxfin", dwg=False)


def test_source_is_never_overwritten(exe: Path, tmp_path: Path) -> None:
    dwg = tmp_path / "a.dwg"
    dwg.write_bytes(b"AC1032")
    with pytest.raises(FinisherError, match="would be overwritten"):
        _finish(dwg, exe, overwrite=True)


def test_existing_outputs_need_overwrite(sheet: Path, exe: Path) -> None:
    _finish(sheet, exe)
    with pytest.raises(FinisherError, match=r"output exists: sld\.dwg, sld\.pdf"):
        _finish(sheet, exe)


def test_overwrite_removes_earlier_outputs_first(sheet: Path, exe: Path) -> None:
    _finish(sheet, exe)
    result = _finish(sheet, exe, FakeCoreConsole(write_dwg=False), overwrite=True)
    assert f"not produced: {result.paths.dwg}" in result.problems


# --- the real process runner (a Python child instead of Core Console) -------------------------


def test_run_process_captures_output_and_exit_code(tmp_path: Path) -> None:
    command = [sys.executable, "-c", "import sys; print('hola'); sys.exit(3)"]
    outcome = run_process(command, tmp_path, 30, tmp_path / "raw.out")
    assert not outcome.timed_out
    assert outcome.exit_code == 3
    assert outcome.output.strip() == b"hola"
    assert outcome.pid is not None
    assert (tmp_path / "raw.out").read_bytes() == outcome.output


def test_run_process_stops_its_own_process_on_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw_output = tmp_path / "raw.out"

    class StartedThenTimed(subprocess.Popen[bytes]):
        """A real process whose timeout starts only once it has printed ``start``.

        Under load the child interpreter can take more than the 1 s timeout just to start, and it
        was then killed before printing anything. Holding the first ``wait`` until ``start`` is in
        the output keeps the real timeout, kill and reap, and makes the captured output certain.
        """

        gated = False

        def wait(self, timeout: float | None = None) -> int:
            if not self.gated:
                self.gated = True
                deadline = time.monotonic() + 60
                while b"start" not in raw_output.read_bytes():
                    if self.poll() is not None or time.monotonic() > deadline:
                        self.kill()
                        pytest.fail("the child process never printed 'start'")
                    time.sleep(0.05)
            return super().wait(timeout)

    monkeypatch.setattr(core_console_module.subprocess, "Popen", StartedThenTimed)
    command = [sys.executable, "-c", "import time; print('start', flush=True); time.sleep(60)"]
    outcome = run_process(command, tmp_path, 1.0, raw_output)
    assert outcome.timed_out
    assert outcome.exit_code is not None
    assert outcome.duration_s < 30
    assert outcome.output.strip() == b"start"


def test_run_process_reports_a_timeout_even_if_reaping_the_killed_process_stalls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class StuckProcess:
        pid = 4242
        returncode = None

        def __init__(self, *args: object, **kwargs: object) -> None:
            self.killed = False

        def wait(self, timeout: float | None = None) -> int:
            raise subprocess.TimeoutExpired("accoreconsole", timeout or 0)

        def kill(self) -> None:
            self.killed = True

    monkeypatch.setattr(core_console_module.subprocess, "Popen", StuckProcess)
    outcome = run_process(["accoreconsole"], tmp_path, 0.01, tmp_path / "raw.out")
    assert outcome.timed_out
    assert outcome.exit_code is None
    assert outcome.pid == 4242
