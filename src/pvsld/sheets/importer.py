"""Import the owner's sheet template: DWG -> DXF with the Core Console, then a neutral DXF.

``pvsld sheet import plantilla.dwg`` writes ``sheet_templates/a3_plantilla_v1.dxf``: the sheet
furniture on house layers with every field as a ``{name}`` placeholder. The source file is only
read; personal data in its fields does not reach the output.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import ezdxf

from pvsld.core.sheet import SheetTemplate, SheetTemplateError
from pvsld.finishers.core_console import _script_path, find_accoreconsole
from pvsld.sheets.loader import DEFINITIONS, read_template, template_path, write_template

DXFOUT_PRECISION = 16


def dxfout_script(target: Path) -> str:
    """Core Console script that saves the open drawing as ``target`` (DXF, 16 decimals)."""
    return "\n".join(
        [
            '(setvar "FILEDIA" 0)',
            "_.DXFOUT",
            _script_path(target),
            str(DXFOUT_PRECISION),
            "_.QUIT",
            "_Y",
            "",
        ]
    )


def dwg_to_dxf(
    dwg: Path, target: Path, *, accoreconsole: Path | None = None, timeout_s: float = 120
) -> Path:
    """Save ``dwg`` as the DXF ``target`` with the local Core Console.

    Raises:
        SheetTemplateError: no Core Console, the process failed or no DXF was written.
    """
    executable = find_accoreconsole(accoreconsole)
    if executable is None:
        raise SheetTemplateError(
            "accoreconsole.exe not found; save the template as DXF in AutoCAD (DXFOUT) instead"
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        script = Path(work) / "dxfout.scr"
        script.write_text(dxfout_script(target.resolve()), encoding="ascii")
        try:
            subprocess.run(
                [str(executable), "/i", str(dwg.resolve()), "/s", str(script)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout_s,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise SheetTemplateError(
                f"Core Console did not finish within {timeout_s:g} s"
            ) from None
    if not target.is_file():
        raise SheetTemplateError(f"Core Console did not write {target}")
    return target


def import_template(
    source: Path,
    name: str,
    output: Path | None = None,
    *,
    accoreconsole: Path | None = None,
) -> tuple[SheetTemplate, Path]:
    """Read the owner's template ``source`` (DWG or DXF) and write its neutral DXF.

    Raises:
        SheetTemplateError: unknown template name, conversion failure, or a source that does not
            match the definition.
    """
    if name not in DEFINITIONS:
        raise SheetTemplateError(f"unknown sheet template {name!r}")
    output = output or template_path(name)
    with tempfile.TemporaryDirectory() as work:
        dxf = source
        if source.suffix.lower() == ".dwg":
            dxf = dwg_to_dxf(source, Path(work) / f"{source.stem}.dxf", accoreconsole=accoreconsole)
        template = read_template(ezdxf.readfile(dxf), DEFINITIONS[name])
    write_template(template, output)
    return template, output
