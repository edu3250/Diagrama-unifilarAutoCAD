"""One-step design (Stage 3.6.1): size, validate, draw, finish and report one installation.

:func:`design_and_draw` is what the plugin's quick mode calls: from a module, a size and
(optionally) the non-sizing sections of the spec, it writes every deliverable into one folder:

* ``unifilar.dxf`` and ``unifilar.png`` (always);
* ``unifilar.dwg`` and ``unifilar.pdf`` plotted by AutoCAD when Core Console is installed and the
  run passes the finisher's checks; otherwise ``unifilar.pdf`` is rendered by pvsld (vector A3,
  black on white), so a user without AutoCAD still gets a printable sheet;
* ``memoria_calculo.xlsx`` and ``.pdf``, ``hoja_de_proyecto.xlsx``, ``resumen_materiales.txt``;
* ``especificacion.yaml``, the validated spec, so a design can be reproduced or edited.

Without a template the quick template (``quick_template.yaml``) supplies the service, grounding
and title block; its personal fields are markers the sheet and the report leave blank.

A request the engine cannot meet is a normal result (``ok`` false, ``stage`` ``"sizing"``), not an
exception, so the caller can explain the rejections. Only a malformed request raises.
"""

from __future__ import annotations

import copy
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any, Literal

import yaml

from pvsld.catalogue.registry import ComponentRegistry
from pvsld.core.validation import ValidationReport
from pvsld.finishers.core_console import (
    AutocadInfo,
    FinisherError,
    FinishOptions,
    Runner,
    detect_autocad,
    finish,
    run_process,
)
from pvsld.report import (
    bom_text,
    build_memoria,
    write_memoria_pdf,
    write_memoria_xlsx,
    write_project_sheet,
)
from pvsld.service import generate_single_line_diagram
from pvsld.sizing import request_from_mapping, size_pv_system
from pvsld.sizing.models import SizingResult

__all__ = [
    "DELIVERABLES",
    "QUICK_TEMPLATE",
    "DesignResult",
    "design_and_draw",
    "load_quick_template",
]

QUICK_TEMPLATE = Path(__file__).with_name("quick_template.yaml")
STEM = "unifilar"
DXF, PNG, DWG, PDF = (f"{STEM}.{suffix}" for suffix in ("dxf", "png", "dwg", "pdf"))
MEMORIA_XLSX, MEMORIA_PDF = "memoria_calculo.xlsx", "memoria_calculo.pdf"
PROJECT_SHEET, BOM_TXT = "hoja_de_proyecto.xlsx", "resumen_materiales.txt"
SPEC_YAML = "especificacion.yaml"
DELIVERABLES = (DXF, DWG, PDF, PNG, MEMORIA_XLSX, MEMORIA_PDF, PROJECT_SHEET, BOM_TXT, SPEC_YAML)
"""Every file a run may write, in the order they are listed to the user."""
_AUTOCAD_WORK = ".autocad"

QUICK_ASSUMPTIONS = (
    "Servicio por omisión: CFE BT 2F-3H 220/127 V, 10 kA de corriente de falla, interruptor "
    "principal de 100 A y centro de carga de 125 A.",
    "Temperaturas por omisión: mínima −3 °C, máxima 38 °C.",
    "Datos personales en blanco: titular, dirección, RPU y responsable se llenan a mano o con la "
    "hoja de proyecto.",
)

Stage = Literal["sizing", "validation", "drawing", "done"]
PdfSource = Literal["autocad", "pvsld"]


def load_quick_template() -> dict[str, Any]:
    """The non-sizing sections of the quick mode (a fresh copy on every call)."""
    data: dict[str, Any] = yaml.safe_load(QUICK_TEMPLATE.read_text(encoding="utf-8"))
    return data


@dataclass(frozen=True)
class DesignResult:
    """Outcome of :func:`design_and_draw`; ``files`` maps each written file name to its path."""

    ok: bool
    stage: Stage
    sizing: SizingResult
    folder: Path
    autocad: AutocadInfo
    quick: bool
    validation: ValidationReport | None = None
    files: dict[str, Path] = field(default_factory=dict)
    pdf_source: PdfSource | None = None
    explanation_es: str = ""
    bom_text: str = ""
    report_ok: bool | None = None
    problems: tuple[str, ...] = ()
    """What went wrong (stage ``drawing``) or what fell back (AutoCAD failed: own PDF instead)."""


def _quick_dates(spec: dict[str, Any], today: date) -> None:
    block = spec["title_block"]
    block["date"] = today
    for revision in block.get("revisions", []):
        revision["date"] = today


def _write_spec(path: Path, spec: Mapping[str, Any]) -> Path:
    path.write_text(yaml.safe_dump(dict(spec), allow_unicode=True, sort_keys=False), "utf-8")
    return path


def _finish_with_autocad(
    folder: Path, autocad: AutocadInfo, runner: Runner
) -> tuple[dict[str, Path], list[str]]:
    """DWG and PDF from Core Console, moved next to the DXF; the work files are removed."""
    work = folder / _AUTOCAD_WORK
    try:
        result = finish(
            folder / DXF,
            work,
            options=FinishOptions(overwrite=True),
            accoreconsole=autocad.executable,
            runner=runner,
        )
        if not result.ok:
            return {}, [
                "AutoCAD did not finish the drawing (" + "; ".join(result.problems[:3]) + ")"
            ]
        files = {}
        for name, produced in ((DWG, result.paths.dwg), (PDF, result.paths.pdf)):
            files[name] = produced.replace(folder / name)
        return files, []
    except (FinisherError, OSError) as error:
        return {}, [f"AutoCAD could not be run: {error}"]
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _own_pdf(folder: Path) -> Path:
    import ezdxf

    from pvsld.backends.preview import write_pdf

    write_pdf(ezdxf.readfile(folder / DXF), folder / PDF)
    return folder / PDF


def design_and_draw(
    values: Mapping[str, Any],
    registry: ComponentRegistry,
    folder: Path,
    *,
    use_autocad: Literal["auto", "never"] = "auto",
    autocad: AutocadInfo | None = None,
    runner: Runner = run_process,
    today: date | None = None,
    base_dir: Path | None = None,
) -> DesignResult:
    """Design one installation and write its deliverables into ``folder`` (created if missing).

    Args:
        values: a sizing request as :func:`pvsld.sizing.request_from_mapping` reads it; without
            ``template`` (or ``template_file``) the quick template is used.
        registry: the component catalogue.
        folder: where the files go; existing files of the same names are replaced.
        use_autocad: ``"never"`` skips Core Console even when it is installed.
        autocad: the detected installation (default: :func:`detect_autocad`).
        runner: the Core Console runner (tests pass a fake).
        today: date of the title block in quick mode (default: today).
        base_dir: folder a relative ``template_file`` is read from.

    Raises:
        SizingInputError: the request is malformed (unknown component, bad template...).
        OSError: a file cannot be written (for example, it is open in AutoCAD or Excel).
    """
    request_values = dict(values)
    quick = "template" not in request_values and "template_file" not in request_values
    if quick:
        request_values["template"] = load_quick_template()
    request = request_from_mapping(request_values, base_dir=base_dir)
    sizing = size_pv_system(request, registry)
    info = autocad if autocad is not None else detect_autocad()
    result = DesignResult(
        ok=False, stage="sizing", sizing=sizing, folder=folder, autocad=info, quick=quick
    )
    selected = sizing.selected
    if selected is None:
        return result

    spec = copy.deepcopy(selected.spec)
    if quick:
        _quick_dates(spec, today or date.today())
    folder.mkdir(parents=True, exist_ok=True)
    generated = generate_single_line_diagram(spec, folder / DXF, png=True, overwrite=True)
    report = generated.validation
    if report.spec is None or report.derived is None or generated.dxf_path is None:
        return replace(result, stage="validation", validation=report)
    files = {DXF: folder / DXF}
    if generated.png_path is not None:
        files[PNG] = generated.png_path
    if not generated.ok:
        problems = generated.readback.problems if generated.readback else ()
        return replace(
            result, stage="drawing", validation=report, files=files, problems=tuple(problems)
        )

    problems: list[str] = []
    pdf_source: PdfSource = "pvsld"
    if info.found and use_autocad == "auto":
        finished, problems = _finish_with_autocad(folder, info, runner)
        files.update(finished)
        if PDF in finished:
            pdf_source = "autocad"
    if pdf_source == "pvsld":
        (folder / DWG).unlink(missing_ok=True)
        files[PDF] = _own_pdf(folder)

    assumptions = (*sizing.assumptions, *(QUICK_ASSUMPTIONS if quick else ()))
    memoria = build_memoria(
        report.spec,
        report.derived,
        report.findings,
        explanation_es=selected.explanation_es,
        assumptions=assumptions,
    )
    summary = bom_text(report.spec, report.derived)
    files[MEMORIA_XLSX] = write_memoria_xlsx(memoria, folder / MEMORIA_XLSX)
    files[MEMORIA_PDF] = write_memoria_pdf(memoria, folder / MEMORIA_PDF)
    files[PROJECT_SHEET] = write_project_sheet(
        folder / PROJECT_SHEET,
        registry,
        report.spec,
        report.derived,
        explanation_es=selected.explanation_es,
    )
    (folder / BOM_TXT).write_text(summary + "\n", encoding="utf-8")
    files[BOM_TXT] = folder / BOM_TXT
    files[SPEC_YAML] = _write_spec(folder / SPEC_YAML, spec)
    ordered = {name: files[name] for name in DELIVERABLES if name in files}
    return replace(
        result,
        ok=True,
        stage="done",
        validation=report,
        files=ordered,
        pdf_source=pdf_source,
        explanation_es=selected.explanation_es,
        bom_text=summary,
        report_ok=memoria.ok,
        problems=tuple(problems),
    )
