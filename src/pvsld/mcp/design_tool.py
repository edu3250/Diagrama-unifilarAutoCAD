"""The one-step tool of the plugin's quick mode (Stage 3.6.1): ``design_and_draw``.

It runs :func:`pvsld.design.design_and_draw` in a staging folder of the output sandbox and, when
the design is complete, publishes every file into ``<output>/<name>/``, one folder per project.
Nothing is published for a design that failed, so a folder only ever holds a coherent set.
"""

from __future__ import annotations

import base64
from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ImageContent
from pydantic import BaseModel, Field

from pvsld.catalogue.registry import ComponentRegistry
from pvsld.design import DELIVERABLES, DesignResult, design_and_draw
from pvsld.design.pipeline import PNG
from pvsld.finishers.core_console import AutocadInfo, Runner, run_process
from pvsld.mcp.models import ValidationOutput, validation_output, validation_text
from pvsld.mcp.preview import shrink_png
from pvsld.mcp.sandbox import OutputSandbox, SandboxError
from pvsld.mcp.sizing_tools import sizing_output, sizing_text
from pvsld.sizing import SizingInputError

__all__ = ["DesignOutput", "default_project_name", "design_text", "run_design"]


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
    except SandboxError as error:
        raise ToolError(str(error)) from error
    except OSError as error:
        raise ToolError(f"cannot write the design: {error}") from error

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
            next_step=(
                "Tell the user in Spanish: the explanation of the inverter as given, the "
                "installation summary (bom_text, in a code block), the folder and its files, and "
                "that the project sheet (hoja_de_proyecto.xlsx) can be edited and returned for a "
                "professional design. Remind them that a responsible engineer must review and "
                "sign the drawing."
            ),
        ),
        image,
    )


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
    lines += [f"file: {path}" for path in output.files]
    if output.bom_text:
        lines.append(output.bom_text)
    lines.append(output.next_step)
    return "\n".join(lines)
