"""Smoke test of an installed wheel, run outside the repository (CI job "package", Stage 3.6.4).

The plugin's server is built by ``uvx`` from a git tag and runs with no repository around it, so
every file the code reads must come from the package. This script fails when one does not:

    python -m venv /tmp/venv && /tmp/venv/bin/pip install dist/pvsld-*.whl
    cd /tmp && /tmp/venv/bin/python -I <repo>/scripts/smoke_installed.py

It checks that pvsld and its data resolve inside the environment, then designs the quick-mode
installation (5 x Jinko 475 W) without AutoCAD and checks every deliverable.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


def main() -> int:
    import pvsld
    from pvsld.catalogue.cli import DEFAULT_RECORDS
    from pvsld.catalogue.local import load_catalogue
    from pvsld.design import design_and_draw
    from pvsld.design.pipeline import DELIVERABLES
    from pvsld.finishers.core_console import AutocadInfo
    from pvsld.mcp.server import _EXAMPLE_SPEC
    from pvsld.resources import PACKAGE_DATA
    from pvsld.sheets.loader import template_path
    from pvsld.symbols.cfe.loader import library_path

    package = Path(pvsld.__file__).resolve().parent
    data = {
        "records": DEFAULT_RECORDS,
        "symbols": library_path(),
        "template": template_path("a3_plantilla_v1"),
        "example": _EXAMPLE_SPEC,
    }
    problems = [
        f"{name}: {path} is not inside the installed package"
        for name, path in data.items()
        if path is None or not Path(path).resolve().is_relative_to(PACKAGE_DATA.resolve())
    ]
    problems += [
        f"{name}: {path} does not exist"
        for name, path in data.items()
        if path and not Path(path).exists()
    ]
    if problems:
        print("\n".join(problems), file=sys.stderr)
        return 1

    registry = load_catalogue(DEFAULT_RECORDS)
    with tempfile.TemporaryDirectory() as folder:
        result = design_and_draw(
            {"module": "JINKO-JKM475N-60HL4", "module_count_min": 5, "module_count_max": 5},
            registry,
            Path(folder) / "project",
            use_autocad="never",
            autocad=AutocadInfo(None),
        )
        if not result.ok:
            print(f"design failed at {result.stage}: {result.problems}", file=sys.stderr)
            return 1
        expected = [name for name in DELIVERABLES if name != "unifilar.dwg"]
        missing = [name for name in expected if not (Path(folder) / "project" / name).is_file()]
        if missing:
            print(f"missing deliverables: {missing}", file=sys.stderr)
            return 1
    print(
        json.dumps(
            {
                "pvsld": str(package),
                "components": len(registry),
                "explanation": result.explanation_es,
                "deliverables": expected,
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
