"""The one-step tools of the plugin: quick mode (Stage 3.6.1) and professional mode (3.6.2).

``design_and_draw`` runs :func:`pvsld.design.design_and_draw` in a staging folder of the output
sandbox and, when the design is complete, publishes every file into ``<output>/<name>/``, one
folder per project. Nothing is published for a design that failed, so a folder only ever holds a
coherent set.

The professional mode works on the project sheet of a project folder,
``<output>/<name>/hoja_de_proyecto.xlsx`` (tools never take paths): ``new_project_sheet`` writes a
blank one, ``design_from_project_sheet`` reads it, and either publishes the design (the sheet's
"Último cálculo" column refreshed) or writes ``hoja_de_proyecto_revisar.xlsx`` beside it, the
user's sheet with the cells to fix in red.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ImageContent
from pydantic import BaseModel, Field

from pvsld.catalogue.registry import ComponentRegistry
from pvsld.design import DELIVERABLES, DesignResult, design_and_draw
from pvsld.design.pipeline import PNG, PROJECT_SHEET
from pvsld.design.pro import ProjectSheetError, design_from_sheet, write_reviewed_sheet
from pvsld.finishers.core_console import AutocadInfo, Runner, run_process
from pvsld.mcp.models import ValidationOutput, validation_output, validation_text
from pvsld.mcp.preview import shrink_png
from pvsld.mcp.sandbox import OutputSandbox, SandboxError
from pvsld.mcp.sizing_tools import sizing_output, sizing_text
from pvsld.report import write_project_sheet
from pvsld.sizing import SizingInputError

__all__ = [
    "REVIEW_SHEET",
    "DesignOutput",
    "default_project_name",
    "design_text",
    "run_design",
    "run_new_sheet",
    "run_pro_design",
]

REVIEW_SHEET = "hoja_de_proyecto_revisar.xlsx"


class DesignOutput(BaseModel):
    """Result of ``design_and_draw``."""

    ok: bool = Field(description="True when every file was written into the project folder.")
    summary: str
    folder: str | None = Field(default=None, description="The project folder.")
    files: list[str] = Field(
        default_factory=list,
        description="Written files: diagram (DXF, DWG with AutoCAD, PDF, PNG), calculation report "
        "(xlsx, pdf), project sheet (xlsx), bill of materials (txt) and the spec (yaml).",
    )
    explanation_es: str = Field(
        default="", description="Why this inverter, in plain Spanish: tell the user as it is."
    )
    bom_text: str = Field(
        default="", description="Spanish installation summary (bill of materials) for the user."
    )
    autocad_es: str = Field(default="", description="Whether AutoCAD was used, in Spanish.")
    pdf_source: Literal["autocad", "pvsld"] | None = Field(
        default=None, description="Who drew the diagram PDF: AutoCAD's plot or pvsld's renderer."
    )
    problems: list[str] = Field(
        default_factory=list,
        description="What failed or fell back (for example AutoCAD failed and pvsld drew the PDF).",
    )
    sizing: str | None = Field(
        default=None, description="When no design fits: the sizing verdict and rejections."
    )
    validation: ValidationOutput | None = None
    issues: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Professional mode: cells of the project sheet to fix (sheet, label, row, "
        "Spanish reason; missing_component when a model is not in the catalogue).",
    )
    missing_components: list[str] = Field(
        default_factory=list,
        description="Models the user wrote that are not in the catalogue: ask for their datasheet.",
    )
    reviewed_sheet: str | None = Field(
        default=None, description="The user's sheet with the cells to fix in red."
    )
    next_step: str


def default_project_name(result: DesignResult) -> str:
    """``sfv_2p38kWp``: the folder name when the user gave none."""
    derived = result.validation.derived if result.validation else None
    kwp = derived.kwp_total if derived else 0.0
    return f"sfv_{kwp:.2f}kWp".replace(".", "p")


def _failure(result: DesignResult) -> DesignOutput:
    if result.stage == "sizing":
        return DesignOutput(
            ok=False,
            summary="NO DESIGN: no configuration of the catalogue meets the rules of this request.",
            sizing=sizing_text(sizing_output(result.sizing)),
            next_step="Explain the rejections to the user in Spanish and propose a change (module "
            "count, target power or another module); nothing was written.",
        )
    if result.stage == "validation" and result.validation is not None:
        return DesignOutput(
            ok=False,
            summary="FAILED: the sized design does not validate; nothing was written.",
            validation=validation_output(result.validation, with_derived=False),
            next_step="This is a defect of the engine, not of the request: report the findings.",
        )
    return DesignOutput(
        ok=False,
        summary="FAILED: the drawing did not pass read-back verification; nothing was written.",
        problems=list(result.problems),
        next_step="This is a defect of the generator: report the problems to the user.",
    )


def run_design(
    box: OutputSandbox,
    registry: ComponentRegistry,
    values: Mapping[str, Any],
    *,
    name: str | None,
    overwrite: bool,
    use_autocad: Literal["auto", "never"],
    max_preview_bytes: int,
    autocad: AutocadInfo | None = None,
    runner: Runner = run_process,
    today: date | None = None,
) -> tuple[DesignOutput, ImageContent | None]:
    """Design, then publish the files into the project folder; the body of the tool.

    Raises:
        ToolError: the request is malformed, the name is refused, the folder already holds a
            design and ``overwrite`` is false, or a file cannot be replaced (open in AutoCAD or
            Excel).
    """
    try:
        if name is not None:
            box.project_dir(name)  # refuse a bad name before the work
        with box.staging() as stage:
            try:
                result = design_and_draw(
                    values,
                    registry,
                    stage / "project",
                    use_autocad=use_autocad,
                    autocad=autocad,
                    runner=runner,
                    today=today,
                )
            except SizingInputError as error:
                raise ToolError(f"invalid design request: {error}") from error
            if not result.ok:
                return _failure(result), None

            folder = box.project_dir(name or default_project_name(result))
            _publish(box, folder, result, overwrite=overwrite)
    except SandboxError as error:
        raise ToolError(str(error)) from error
    except OSError as error:
        raise ToolError(f"cannot write the design: {error}") from error
    return _success(result, folder, max_preview_bytes, QUICK_NEXT_STEP)


QUICK_NEXT_STEP = (
    "Tell the user in Spanish: the explanation of the inverter as given, the installation "
    "summary (bom_text, in a code block), the folder and its files, and that the project sheet "
    "(hoja_de_proyecto.xlsx) can be edited and returned for a professional design. Remind them "
    "that a responsible engineer must review and sign the drawing."
)
PRO_NEXT_STEP = (
    "Tell the user in Spanish: the explanation of the inverter as given, the installation "
    "summary (bom_text, in a code block), the folder and its files. Remind them that a "
    "responsible engineer must review and sign the drawing."
)


def _publish(box: OutputSandbox, folder: Path, result: DesignResult, *, overwrite: bool) -> None:
    """Move the staged files into the project folder; stale deliverables of a replaced design go."""
    existing = [n for n in DELIVERABLES if (folder / n).exists()]
    if existing and not overwrite:
        raise ToolError(
            f"the folder {folder.name} already holds a design ({', '.join(existing)}). "
            "Call again with overwrite=true to replace it (only if the user asked for "
            "that), or choose another name."
        )
    folder.mkdir(exist_ok=True)
    for stale in set(existing) - set(result.files):
        (folder / stale).unlink()
    for file_name, staged in result.files.items():
        box.publish(staged, folder / file_name)


def _success(
    result: DesignResult, folder: Path, max_preview_bytes: int, next_step: str
) -> tuple[DesignOutput, ImageContent | None]:
    image = None
    if PNG in result.files:
        shrunk = shrink_png((folder / PNG).read_bytes(), max_preview_bytes)
        if shrunk is not None:
            image = ImageContent(
                type="image",
                data=base64.b64encode(shrunk.data).decode("ascii"),
                mime_type="image/png",
            )
    fell_back = " (AutoCAD failed: pvsld drew the PDF)" if result.problems else ""
    return (
        DesignOutput(
            ok=True,
            summary=f"OK: {len(result.files)} files written to {folder}{fell_back}.",
            folder=str(folder),
            files=[str(folder / n) for n in result.files],
            explanation_es=result.explanation_es,
            bom_text=result.bom_text,
            autocad_es=result.autocad.describe_es(),
            pdf_source=result.pdf_source,
            problems=list(result.problems),
            next_step=next_step,
        ),
        image,
    )


def run_new_sheet(
    box: OutputSandbox, registry: ComponentRegistry, *, name: str, overwrite: bool
) -> DesignOutput:
    """Write a blank project sheet (AUTO everywhere) into the project folder ``name``."""
    try:
        folder = box.project_dir(name)
        target = folder / PROJECT_SHEET
        if target.exists() and not overwrite:
            raise ToolError(
                f"{name}/{PROJECT_SHEET} already exists. Call again with overwrite=true to "
                "replace it (only if the user asked for that), or choose another name."
            )
        with box.staging() as stage:
            staged = write_project_sheet(stage / PROJECT_SHEET, registry)
            folder.mkdir(exist_ok=True)
            box.publish(staged, target)
    except SandboxError as error:
        raise ToolError(str(error)) from error
    except OSError as error:
        raise ToolError(f"cannot write the project sheet: {error}") from error
    return DesignOutput(
        ok=True,
        summary=f"OK: blank project sheet written to {target}.",
        folder=str(folder),
        files=[str(target)],
        next_step=(
            "Tell the user in Spanish where the sheet is: fill in the yellow cells (AUTO lets "
            "the calculation decide), save it in the same place and ask for the design of "
            f"project {name}; then call design_from_project_sheet."
        ),
    )


def run_pro_design(
    box: OutputSandbox,
    registry: ComponentRegistry,
    *,
    name: str,
    use_autocad: Literal["auto", "never"],
    max_preview_bytes: int,
    autocad: AutocadInfo | None = None,
    runner: Runner = run_process,
    today: date | None = None,
) -> tuple[DesignOutput, ImageContent | None]:
    """Design from ``<output>/<name>/hoja_de_proyecto.xlsx``; the body of the tool.

    Raises:
        ToolError: the name is refused, the folder has no project sheet, the file is not one, or
            a file cannot be written (open in Excel or AutoCAD).
    """
    try:
        folder = box.project_dir(name)
        sheet = folder / PROJECT_SHEET
        if not sheet.is_file():
            raise ToolError(
                f"there is no {PROJECT_SHEET} in the project folder {name}. Ask the user to "
                "save the filled sheet there, or call new_project_sheet for a blank one."
            )
        with box.staging() as stage:
            try:
                pro = design_from_sheet(
                    sheet,
                    registry,
                    stage / "project",
                    use_autocad=use_autocad,
                    autocad=autocad,
                    runner=runner,
                    today=today,
                )
            except ProjectSheetError as error:
                raise ToolError(str(error)) from error
            except SizingInputError as error:
                raise ToolError(f"the sheet cannot be designed: {error}") from error
            if pro.issues:
                reviewed = write_reviewed_sheet(sheet, stage / REVIEW_SHEET, pro.issues)
                box.publish(reviewed, folder / REVIEW_SHEET)
                issues = [issue.to_dict() for issue in pro.issues]
                missing = list(pro.missing_components)
                return (
                    DesignOutput(
                        ok=False,
                        summary=(
                            f"TO FIX: {len(issues)} cell(s) of the project sheet; nothing was "
                            f"designed. {REVIEW_SHEET} marks them in red."
                        ),
                        folder=str(folder),
                        issues=issues,
                        missing_components=missing,
                        reviewed_sheet=str(folder / REVIEW_SHEET),
                        next_step=(
                            "Tell the user in Spanish each cell to fix and why (sheet > label: "
                            "reason), and that the marked copy is "
                            f"{REVIEW_SHEET}. For a missing component, ask for its datasheet "
                            "(PDF) to add it to the local catalogue. After the user corrects "
                            f"{PROJECT_SHEET}, call this tool again."
                        ),
                    ),
                    None,
                )
            assert pro.design is not None
            if not pro.design.ok:
                return _failure(pro.design), None
            _publish(box, folder, pro.design, overwrite=True)
            (folder / REVIEW_SHEET).unlink(missing_ok=True)
    except SandboxError as error:
        raise ToolError(str(error)) from error
    except OSError as error:
        raise ToolError(f"cannot write the design: {error}") from error
    return _success(pro.design, folder, max_preview_bytes, PRO_NEXT_STEP)


def design_text(output: DesignOutput) -> str:
    """Text content of the result (the preview image, when any, is a separate block)."""
    lines = [output.summary]
    if output.sizing:
        lines.append(output.sizing)
    if output.validation is not None:
        lines.append(validation_text(output.validation))
    if output.explanation_es:
        lines.append(f"why (tell the user): {output.explanation_es}")
    if output.autocad_es:
        lines.append(f"autocad: {output.autocad_es}")
    lines += [f"problem: {problem}" for problem in output.problems]
    lines += [
        f"fix {i['sheet']} > {i['label']} (row {i['row']}): {i['message_es']}"
        for i in output.issues
    ]
    lines += [f"missing component: {model}" for model in output.missing_components]
    if output.reviewed_sheet:
        lines.append(f"reviewed sheet: {output.reviewed_sheet}")
    lines += [f"file: {path}" for path in output.files]
    if output.bom_text:
        lines.append(output.bom_text)
    lines.append(output.next_step)
    return "\n".join(lines)
