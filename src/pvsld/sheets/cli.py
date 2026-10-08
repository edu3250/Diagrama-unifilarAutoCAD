"""``pvsld sheet``: import and check the owner's sheet template.

Usage::

    pvsld sheet import SOURCE.dwg|SOURCE.dxf [--name a3_plantilla_v1] [-o PATH]
    pvsld sheet check [--name a3_plantilla_v1] [PATH]

``import`` converts a DWG with the local Core Console, checks it against the template definition
and writes the neutral DXF the generator reads (default ``sheet_templates/<name>.dxf`` or
``$PVSLD_SHEET_TEMPLATE``). ``check`` loads a template DXF and reports its fields.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from pvsld.core.sheet import SheetTemplateError
from pvsld.sheets.a3_plantilla_v1 import NAME as DEFAULT_NAME
from pvsld.sheets.importer import import_template
from pvsld.sheets.loader import load_sheet_template


def _import(args: argparse.Namespace) -> int:
    try:
        template, output = import_template(args.source, args.name, args.output)
    except SheetTemplateError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"wrote {output}: {len(template.fields)} fields, {len(template.texts)} fixed texts, "
        f"{len(template.lines) + len(template.polylines) + len(template.circles)} lines and shapes"
    )
    return 0


def _check(args: argparse.Namespace) -> int:
    try:
        template = load_sheet_template(args.name, args.path)
    except SheetTemplateError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"OK: {template.name} with {len(template.fields)} fields")
    return 0


def register(subcommands: Any) -> None:
    """Add the ``sheet`` command group to the ``pvsld`` parser."""
    sheet = subcommands.add_parser(
        "sheet",
        help="import and check the owner's sheet template",
        description="Work with the sheet template of layout a3_plantilla_v1.",
    )
    actions = sheet.add_subparsers(dest="sheet_command", required=True)
    imp = actions.add_parser(
        "import",
        help="convert the owner's template (DWG or DXF) to the neutral template DXF",
        description="Read the template, check it against its definition and write a neutral DXF "
        "(fields as placeholders, no personal data, no drawing metadata).",
    )
    imp.add_argument("source", type=Path, metavar="SOURCE", help="template DWG or DXF")
    imp.add_argument("--name", default=DEFAULT_NAME, help=f"template name (default {DEFAULT_NAME})")
    imp.add_argument(
        "-o", "--output", type=Path, default=None, metavar="PATH", help="neutral DXF to write"
    )
    imp.set_defaults(run=_import)
    check = actions.add_parser("check", help="load a template DXF and report its fields")
    check.add_argument("path", type=Path, nargs="?", default=None, metavar="PATH")
    check.add_argument(
        "--name", default=DEFAULT_NAME, help=f"template name (default {DEFAULT_NAME})"
    )
    check.set_defaults(run=_check)
