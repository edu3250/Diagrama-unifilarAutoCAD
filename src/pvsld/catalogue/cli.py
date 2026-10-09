"""``pvsld catalogue``: validate, list and show the component records.

Usage::

    pvsld catalogue validate [PATH] [--require-reviewed]
    pvsld catalogue list [--records DIR] [--type TYPE] [--manufacturer NAME] [--include-unreviewed]
    pvsld catalogue show ID [--records DIR] [--include-unreviewed]

``PATH`` is a records folder (default ``datasheets/records``) or one record file, for example a
draft that has not been moved into the catalogue yet. ``validate`` exits with 1 when any record is
invalid; ``--require-reviewed`` also fails while a record has no ``reviewed_by``. ``list`` and
``show`` see reviewed records only, unless ``--include-unreviewed`` is given.
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

from pvsld.catalogue.conductors import Cable
from pvsld.catalogue.errors import CatalogueError, UnknownComponentError
from pvsld.catalogue.inverters import Inverter
from pvsld.catalogue.modules import PVModule
from pvsld.catalogue.protection import DcBreaker, DcFuse
from pvsld.catalogue.registry import RECORD_FOLDERS, Component, ComponentRegistry, load_records

DEFAULT_RECORDS = Path("datasheets") / "records"


def _rating(component: Component) -> str:
    if isinstance(component, PVModule):
        return f"{component.pmax_w:g} Wp"
    if isinstance(component, Inverter):
        return (
            f"{component.rated_ac_power_w / 1000:g} kW AC, "
            f"{component.recommended_max_pv_power_wp / 1000:g} kWp DC max"
        )
    if isinstance(component, Cable):
        return f"{component.size} {component.outer_diameter_mm:g} mm"
    if isinstance(component, DcFuse):
        return f"{component.rated_current_a:g} A {component.operating_class}"
    assert isinstance(component, DcBreaker)
    return f"{component.rated_current_a:g} A"


def _fail(error: CatalogueError) -> int:
    print(f"FAILED: {len(error.problems)} problem(s)", file=sys.stderr)
    for problem in error.problems:
        print(f"  {problem}", file=sys.stderr)
    return 1


def _validate(args: argparse.Namespace) -> int:
    try:
        records = load_records(args.path)
    except CatalogueError as error:
        return _fail(error)
    counts: Counter[str] = Counter()
    unreviewed = []
    for record in records:
        counts[record.family.component_type] += len(record.family.variants)
        if not record.family.source.reviewed:
            unreviewed.append(record)
    breakdown = ", ".join(f"{n} {kind}" for kind, n in sorted(counts.items())) or "no components"
    print(
        f"OK: {args.path}: {len(records)} record(s), {sum(counts.values())} component(s) "
        f"({breakdown}); {len(unreviewed)} unreviewed"
    )
    for record in unreviewed:
        print(f"  unreviewed: {record.path}", file=sys.stderr if args.require_reviewed else None)
    return 1 if args.require_reviewed and unreviewed else 0


def _load(args: argparse.Namespace) -> ComponentRegistry:
    return ComponentRegistry.load(args.records, include_unreviewed=args.include_unreviewed)


def _list(args: argparse.Namespace) -> int:
    try:
        registry = _load(args)
    except CatalogueError as error:
        return _fail(error)
    components = registry.find(component_type=args.type, manufacturer=args.manufacturer)
    rows = [
        (c.component_id, c.component_type, c.manufacturer, _rating(c), _status(c))
        for c in components
    ]
    header = ("ID", "TYPE", "MANUFACTURER", "RATING", "STATUS")
    widths = [max(len(row[i]) for row in [header, *rows]) for i in range(len(header))]
    for row in [header, *rows] if rows else []:
        print(
            "  ".join(cell.ljust(width) for cell, width in zip(row, widths, strict=True)).rstrip()
        )
    print(f"{len(rows)} component(s)")
    if registry.skipped_unreviewed:
        print(
            f"{len(registry.skipped_unreviewed)} unreviewed record(s) skipped "
            f"({', '.join(registry.skipped_unreviewed)}); use --include-unreviewed",
            file=sys.stderr,
        )
    return 0


def _status(component: Component) -> str:
    return "reviewed" if component.reviewed else "UNREVIEWED"


def _show(args: argparse.Namespace) -> int:
    try:
        component = _load(args).get(args.component_id)
    except CatalogueError as error:
        return _fail(error)
    except UnknownComponentError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    data: dict[str, Any] = component.model_dump(mode="json", exclude_none=True)
    data["source"] = component.source.model_dump(mode="json")  # keep reviewed_by: null visible
    print(f"# {component.component_id} ({component.component_type}, {_status(component)})")
    print(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), end="")
    return 0


def register(subcommands: Any) -> None:
    """Add the ``catalogue`` command group to the ``pvsld`` parser."""
    catalogue = subcommands.add_parser(
        "catalogue",
        help="validate, list and show the component catalogue (datasheet records)",
        description="Work with the YAML component records in datasheets/records (ADR-0004).",
    )
    actions = catalogue.add_subparsers(dest="catalogue_command", required=True)

    validate = actions.add_parser(
        "validate",
        help="validate a records folder or one record file",
        description=(
            "Check every record against the schema and the plausibility rules; the exit code is "
            "1 when a record is invalid. Drafts outside the catalogue can be validated one by one."
        ),
    )
    validate.add_argument(
        "path",
        type=Path,
        nargs="?",
        default=DEFAULT_RECORDS,
        metavar="PATH",
        help=f"records folder or record file (default {DEFAULT_RECORDS})",
    )
    validate.add_argument(
        "--require-reviewed",
        action="store_true",
        help="also fail while a record has no reviewed_by",
    )
    validate.set_defaults(run=_validate)

    for name, help_text in (("list", "list the components"), ("show", "print one component")):
        action = actions.add_parser(name, help=help_text, description=help_text.capitalize() + ".")
        action.add_argument(
            "--records",
            type=Path,
            default=DEFAULT_RECORDS,
            metavar="DIR",
            help=f"records folder (default {DEFAULT_RECORDS})",
        )
        action.add_argument(
            "--include-unreviewed",
            action="store_true",
            help="also load records the owner has not reviewed (development only)",
        )
        if name == "list":
            action.add_argument("--type", choices=sorted(RECORD_FOLDERS), help="only this type")
            action.add_argument("--manufacturer", help="only this manufacturer (any case)")
            action.set_defaults(run=_list)
        else:
            action.add_argument(
                "component_id", metavar="ID", help="component_id, e.g. SUNTREE-SL7N-63-16A"
            )
            action.set_defaults(run=_show)
