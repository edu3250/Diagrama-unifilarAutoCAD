"""Stage 3.6.1: the one-step design (``pvsld.design``), its MCP tool and CLI, the pvsld PDF and
the AutoCAD detection.

The fixture catalogue keeps the results stable; Core Console is the fake runner, so the tests run
the same with or without AutoCAD on the machine.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import ezdxf
import pytest
import yaml
from mcp.server.mcpserver.exceptions import ToolError

from pvsld.backends.preview import render_pdf
from pvsld.cli import main
from pvsld.core.validation import validate_pv_design
from pvsld.design import DELIVERABLES, DesignResult, design_and_draw, load_quick_template
from pvsld.finishers.core_console import AutocadInfo, detect_autocad
from pvsld.finishers.fake import FakeCoreConsole
from pvsld.finishers.outputs import inspect_pdf
from pvsld.mcp.design_tool import design_text, run_design
from pvsld.mcp.sandbox import OutputSandbox, SandboxError
from pvsld.mcp.server import create_server
from pvsld.sizing import SizingInputError
from sizing_helpers import ET_550, FIXTURE_RECORDS, registry
from test_mcp_server import call, images_of, text_of

TODAY = date(2026, 10, 9)
QUICK = {"module": ET_550, "module_count_min": 8, "module_count_max": 8}
NO_AUTOCAD = AutocadInfo(None)
WITHOUT_DWG = [name for name in DELIVERABLES if name != "unifilar.dwg"]


def _fake_autocad(tmp_path: Path) -> AutocadInfo:
    executable = tmp_path / "AutoCAD 2027" / "accoreconsole.exe"
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.write_bytes(b"")
    return AutocadInfo(executable, "AutoCAD 2027")


def _design(folder: Path, values: dict[str, Any] | None = None, **options: Any) -> DesignResult:
    options.setdefault("autocad", NO_AUTOCAD)
    return design_and_draw(values or QUICK, registry(), folder, today=TODAY, **options)


@pytest.fixture(scope="module")
def quick(tmp_path_factory: pytest.TempPathFactory) -> DesignResult:
    """One quick design without AutoCAD, shared by the read-only checks."""
    return _design(tmp_path_factory.mktemp("quick") / "project")


# --- the pipeline ---------------------------------------------------------------------------------


def test_a_quick_design_writes_every_deliverable_without_autocad(quick: DesignResult) -> None:
    assert quick.ok
    assert quick.stage == "done"
    assert quick.quick
    assert list(quick.files) == WITHOUT_DWG
    assert all(path.is_file() and path.parent == quick.folder for path in quick.files.values())
    assert quick.pdf_source == "pvsld"
    assert quick.problems == ()
    assert quick.report_ok is True


def test_the_quick_design_explains_the_inverter_and_summarises_the_materials(
    quick: DesignResult,
) -> None:
    assert quick.explanation_es.startswith("Se eligió el inversor")
    assert quick.bom_text.startswith("RESUMEN DE LA INSTALACIÓN")
    assert "Fusible gPV" in quick.bom_text
    assert "DPS de CD" in quick.bom_text
    written = quick.files["resumen_materiales.txt"].read_text(encoding="utf-8")
    assert written == quick.bom_text + "\n"


def test_the_written_spec_validates_and_carries_the_quick_defaults(quick: DesignResult) -> None:
    spec = yaml.safe_load(quick.files["especificacion.yaml"].read_text(encoding="utf-8"))
    report = validate_pv_design(spec)
    assert report.ok
    assert report.spec is not None
    assert report.spec.utility.system == "2F-3H"
    assert report.spec.title_block.date == TODAY
    assert report.spec.project.name.endswith(" kWp")
    assert "{kwp}" not in report.spec.project.name
    assert report.spec.project.client.name == "SIN DATOS"
    assert [s.id for s in report.spec.dc_bos.spds] == ["DPS-CD1"]


def test_the_pvsld_pdf_is_one_a3_page(quick: DesignResult) -> None:
    info = inspect_pdf(quick.files["unifilar.pdf"])
    assert info.header_ok
    assert info.pages == 1
    ((width, height),) = info.page_sizes_mm
    assert (round(width), round(height)) == (420, 297)
    assert info.creator == "pvsld"


def test_the_quick_template_needs_only_the_equipment() -> None:
    template = load_quick_template()
    assert template["layout"]["template"] == "a3_plantilla_v1"
    assert "{kwp}" in template["project"]["name"]
    assert load_quick_template() is not template  # a fresh copy each time


def test_a_given_template_replaces_the_quick_defaults(tmp_path: Path) -> None:
    template = load_quick_template()
    template["utility"]["available_fault_current_ka"] = 22
    result = _design(tmp_path, {**QUICK, "template": template}, use_autocad="never")
    assert result.ok
    assert not result.quick
    assert result.validation is not None
    assert result.validation.spec is not None
    assert result.validation.spec.utility.available_fault_current_ka == 22


def test_autocad_finishes_the_drawing_when_it_is_installed(tmp_path: Path) -> None:
    runner = FakeCoreConsole()
    result = _design(tmp_path / "p", autocad=_fake_autocad(tmp_path), runner=runner)
    assert result.ok
    assert result.pdf_source == "autocad"
    assert list(result.files) == list(DELIVERABLES)
    assert result.files["unifilar.pdf"].read_bytes().startswith(b"%PDF")
    assert len(runner.calls) == 1
    assert not (tmp_path / "p" / ".autocad").exists()  # no Core Console work files are left


def test_a_failed_autocad_run_falls_back_to_the_pvsld_pdf(tmp_path: Path) -> None:
    result = _design(
        tmp_path / "p", autocad=_fake_autocad(tmp_path), runner=FakeCoreConsole(exit_code=1)
    )
    assert result.ok
    assert result.pdf_source == "pvsld"
    assert "unifilar.dwg" not in result.files
    assert not (tmp_path / "p" / "unifilar.dwg").exists()
    assert result.problems
    assert result.problems[0].startswith("AutoCAD did not finish the drawing")


def test_never_skips_an_installed_autocad(tmp_path: Path) -> None:
    runner = FakeCoreConsole()
    result = _design(
        tmp_path / "p", autocad=_fake_autocad(tmp_path), runner=runner, use_autocad="never"
    )
    assert result.ok
    assert result.pdf_source == "pvsld"
    assert runner.calls == []


def test_a_request_no_configuration_meets_is_a_result_and_writes_nothing(tmp_path: Path) -> None:
    result = _design(tmp_path / "p", {"module": ET_550, "module_count_min": 90})
    assert not result.ok
    assert result.stage == "sizing"
    assert result.sizing.selected is None
    assert result.files == {}
    assert not (tmp_path / "p").exists()


def test_a_malformed_request_raises(tmp_path: Path) -> None:
    with pytest.raises(SizingInputError):
        _design(tmp_path, {"module": "NO-SUCH-MODULE", "module_count_min": 8})


# --- PDF and AutoCAD detection ------------------------------------------------------------------


def test_the_pdf_is_byte_identical_for_the_same_drawing(quick: DesignResult) -> None:
    document = ezdxf.readfile(quick.files["unifilar.dxf"])
    assert render_pdf(document) == render_pdf(document)


def test_detect_autocad_names_the_release(tmp_path: Path) -> None:
    info = _fake_autocad(tmp_path)
    found = detect_autocad(environ={}, program_dirs=[info.executable.parent])  # type: ignore[union-attr]
    assert found.found
    assert found.release == "AutoCAD 2027"
    assert "DWG" in found.describe_es()


def test_detect_autocad_reports_a_machine_without_it(tmp_path: Path) -> None:
    missing = detect_autocad(environ={}, program_dirs=[tmp_path])
    assert not missing.found
    assert missing.release is None
    assert "DXF" in missing.describe_es()


def test_a_project_folder_name_is_validated(tmp_path: Path) -> None:
    box = OutputSandbox.at(tmp_path)
    assert box.project_dir("casa_lopez") == tmp_path.resolve() / "casa_lopez"
    for bad in ("..", "a/b", "CON", "con espacio"):
        with pytest.raises(SandboxError):
            box.project_dir(bad)


# --- MCP tool -------------------------------------------------------------------------------------


def _run(box: OutputSandbox, **options: Any) -> Any:
    options.setdefault("name", None)
    options.setdefault("overwrite", False)
    return run_design(
        box,
        registry(),
        options.pop("values", QUICK),
        use_autocad="auto",
        max_preview_bytes=62_000,
        autocad=options.pop("autocad", NO_AUTOCAD),
        today=TODAY,
        **options,
    )


def test_the_tool_publishes_one_folder_per_project(tmp_path: Path) -> None:
    box = OutputSandbox.at(tmp_path)
    output, image = _run(box, name="casa")
    assert output.ok
    folder = tmp_path.resolve() / "casa"
    assert output.folder == str(folder)
    assert sorted(p.name for p in folder.iterdir()) == sorted(WITHOUT_DWG)
    assert [Path(f).name for f in output.files] == WITHOUT_DWG
    assert image is not None
    assert not [p for p in tmp_path.iterdir() if p.name.startswith(".pvsld-staging")]
    text = design_text(output)
    assert "why (tell the user): Se eligió" in text
    assert "RESUMEN DE LA INSTALACIÓN" in text


def test_the_default_folder_is_named_after_the_power(tmp_path: Path) -> None:
    output, _ = _run(OutputSandbox.at(tmp_path))
    assert output.ok
    assert output.folder is not None
    assert Path(output.folder).name.startswith("sfv_")
    assert Path(output.folder).name.endswith("kWp")


def test_an_existing_design_is_only_replaced_with_overwrite(tmp_path: Path) -> None:
    box = OutputSandbox.at(tmp_path)
    _run(box, name="casa", autocad=_fake_autocad(tmp_path), runner=FakeCoreConsole())
    assert (tmp_path / "casa" / "unifilar.dwg").exists()
    with pytest.raises(ToolError, match="overwrite=true"):
        _run(box, name="casa")
    output, _ = _run(box, name="casa", overwrite=True)
    assert output.ok
    assert not (tmp_path / "casa" / "unifilar.dwg").exists()  # stale: this run had no AutoCAD


def test_the_tool_refuses_a_bad_name_before_designing(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="invalid name"):
        _run(OutputSandbox.at(tmp_path), name="../fuera")


def test_no_configuration_is_reported_with_the_rejections(tmp_path: Path) -> None:
    output, image = _run(
        OutputSandbox.at(tmp_path), values={"module": ET_550, "module_count_min": 90}
    )
    assert not output.ok
    assert image is None
    assert output.sizing is not None
    assert "REJECTED" in output.sizing
    assert not [p for p in tmp_path.iterdir() if not p.name.startswith(".")]


def test_design_and_draw_through_an_mcp_client(tmp_path: Path) -> None:
    server = create_server(OutputSandbox.at(tmp_path / "out"), catalogue_dir=FIXTURE_RECORDS)
    result = call(server, "design_and_draw", {**QUICK, "name": "demo", "use_autocad": "never"})
    assert not result.is_error
    data = result.structured_content
    assert data is not None
    assert data["ok"] is True
    assert data["pdf_source"] == "pvsld"
    assert data["explanation_es"]
    assert len(images_of(result)) == 1
    assert "file: " in text_of(result)
    assert (tmp_path / "out" / "demo" / "memoria_calculo.xlsx").is_file()


def test_an_unknown_module_is_a_tool_error(tmp_path: Path) -> None:
    server = create_server(OutputSandbox.at(tmp_path / "out"), catalogue_dir=FIXTURE_RECORDS)
    result = call(server, "design_and_draw", {"module": "NO-SUCH", "use_autocad": "never"})
    assert result.is_error
    assert "invalid design request" in text_of(result)


# --- CLI ------------------------------------------------------------------------------------------


def test_pvsld_design_writes_the_project_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "request.yaml"
    request.write_text(yaml.safe_dump(QUICK), encoding="utf-8")
    out = tmp_path / "p"
    argv = ["design", str(request), "-o", str(out), "--no-autocad", "--catalogue"]
    assert main([*argv, str(FIXTURE_RECORDS)]) == 0
    printed = capsys.readouterr().out
    assert printed.startswith("why: Se eligió")
    assert sorted(p.name for p in out.iterdir()) == sorted(WITHOUT_DWG)


def test_pvsld_design_fails_when_nothing_fits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    request = tmp_path / "request.yaml"
    request.write_text(yaml.safe_dump({"module": ET_550, "module_count_min": 90}), "utf-8")
    argv = ["design", str(request), "-o", str(tmp_path / "p"), "--no-autocad", "--catalogue"]
    assert main([*argv, str(FIXTURE_RECORDS)]) == 1
    assert capsys.readouterr().err
