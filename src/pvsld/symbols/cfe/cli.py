"""``pvsld symbols``: build, list and validate the CFE symbol library (ADR-0005).

Usage::

    pvsld symbols build [-o symbols/pvsld-symbols-cfe.dxf] [--png out/legend.png] [--check]
    pvsld symbols list [--json]
    pvsld symbols validate [PATH] [--no-fresh-check]

``build`` writes the deterministic DXF (and, with ``--png``, a picture of each ``Legend`` sheet for
visual review: ``name-1.png``, ``name-2.png``... when there are several). With ``--check`` it
writes nothing and exits 1 when the file on disk differs from what the definitions render, which is
the CI guard against a stale committed library. ``validate`` audits the DXF and checks it against
the definitions; the exit code is 1 on any problem.
The heavy imports (ezdxf, matplotlib) happen inside the handlers so ``pvsld --version`` stays fast.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

DEFAULT_FILE = Path("symbols") / "pvsld-symbols-cfe.dxf"
PNG_DPI = 110


def _build(args: argparse.Namespace) -> int:
    from pvsld.backends.base import sha256_hex
    from pvsld.symbols.cfe.build import LEGEND_LAYOUT, build_document, render_library

    data = render_library()
    target: Path = args.output
    if args.check:
        current = target.read_bytes() if target.is_file() else None
        if current != data:
            print(
                f"{target} is {'missing' if current is None else 'stale'}: "
                "run `pvsld symbols build` and commit the result",
                file=sys.stderr,
            )
            return 1
        print(f"{target} is up to date (sha256 {sha256_hex(data)})")
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    print(f"wrote {target} ({len(data)} bytes, sha256 {sha256_hex(data)})")
    if args.png is not None:
        from pvsld.backends.preview import write_png

        doc = build_document()
        sheets = [n for n in doc.layouts.names() if n.startswith(LEGEND_LAYOUT)]
        for index, layout in enumerate(sorted(sheets), start=1):
            target_png = (
                args.png
                if len(sheets) == 1
                else args.png.with_name(f"{args.png.stem}-{index}{args.png.suffix}")
            )
            png = write_png(doc, target_png, dpi=PNG_DPI, layout_name=layout)
            print(f"wrote {target_png} ({len(png)} bytes, layout {layout})")
    return 0


def _list(args: argparse.Namespace) -> int:
    from pvsld.symbols.cfe.definitions import LIBRARY
    from pvsld.symbols.cfe.model import LIBRARY_VERSION

    if args.json:
        print(
            json.dumps(
                {"version": LIBRARY_VERSION, "symbols": [s.to_dict() for s in LIBRARY]},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    print(f"pvsld symbol library v{LIBRARY_VERSION}: {len(LIBRARY)} blocks")
    for spec in LIBRARY:
        ports = ",".join(p.id for p in spec.ports) or "-"
        print(f"  {spec.name:<20} {spec.description_es}  [{spec.source}]  ports: {ports}")
    return 0


def _validate(args: argparse.Namespace) -> int:
    from pvsld.symbols.cfe.validate import validate_file

    problems = validate_file(args.path, check_fresh=not args.no_fresh_check)
    if problems:
        print(f"FAILED: {len(problems)} problem(s) in {args.path}", file=sys.stderr)
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1
    print(f"OK: {args.path} is a valid CFE symbol library")
    return 0


def register(subcommands: Any) -> None:
    """Add the ``symbols`` command group to the ``pvsld`` parser."""
    symbols = subcommands.add_parser(
        "symbols",
        help="build, list and validate the CFE symbol library (DXF blocks and legend)",
        description="Work with the symbol library of ADR-0005 (symbols/pvsld-symbols-cfe.dxf).",
    )
    actions = symbols.add_subparsers(dest="symbols_command", required=True)

    build = actions.add_parser(
        "build",
        help="write the deterministic library DXF",
        description="Render the definitions to a byte-identical DXF R2018 with the Legend layout.",
    )
    build.add_argument(
        "-o",
        "--output",
        type=Path,
        default=DEFAULT_FILE,
        metavar="PATH",
        help=f"output file (default {DEFAULT_FILE})",
    )
    build.add_argument("--png", type=Path, metavar="PATH", help="also render the Legend to a PNG")
    build.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 when the output file is missing or stale",
    )
    build.set_defaults(run=_build)

    listing = actions.add_parser("list", help="list the blocks", description="List the blocks.")
    listing.add_argument("--json", action="store_true", help="print the library as JSON")
    listing.set_defaults(run=_list)

    validate = actions.add_parser(
        "validate",
        help="audit a library DXF and check it against the definitions",
        description="Audit the DXF and check blocks, attributes, ports, sources and the Legend.",
    )
    validate.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=DEFAULT_FILE,
        metavar="PATH",
        help=f"library DXF (default {DEFAULT_FILE})",
    )
    validate.add_argument(
        "--no-fresh-check",
        action="store_true",
        help="do not require the bytes to equal the rendered definitions",
    )
    validate.set_defaults(run=_validate)
