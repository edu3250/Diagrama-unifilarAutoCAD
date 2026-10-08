"""Command-line interface of ``pvsld``.

Usage::

    pvsld --version
    pvsld validate examples/residential_7p7kwp.yaml [--json]
    pvsld generate examples/residential_7p7kwp.yaml -o out/sld.dxf [--png]
    pvsld finish out/sld.dxf [-d out/finished] [--no-pdf] [--json]
    pvsld catalogue validate [PATH] | list [--type T] | show ID
    pvsld size REQUEST.yaml [--catalogue DIR] [--include-unreviewed] [-o SPEC.yaml] [--json]
    pvsld symbols build [-o PATH] [--png PATH] [--check] | list [--json] | validate [PATH]

``validate`` parses the specification against the parameter model and runs the rule pack
``mx-gd-2026.10``; the exit code is 1 when a rule of severity ``E`` fails. ``generate`` validates
again, writes the DXF R2018 sheet (and a PNG preview with ``--png``) and verifies the written file.
``finish`` turns a DXF into DWG 2018 and a PDF with the local AutoCAD Core Console (Windows, a
licensed full AutoCAD); the exit code is 1 unless every output was produced and checked.
``catalogue`` works with the component records in ``datasheets/records`` (see
:mod:`pvsld.catalogue.cli`). ``size`` runs the sizing engine (:mod:`pvsld.sizing`) on a request
file and prints the selection, the ranked alternatives and why every other configuration was
rejected; the exit code is 1 when no configuration survives. ``-o`` writes the selected
parameter specification, ready for ``validate`` and ``generate``. ``symbols`` builds, lists
and validates the CFE symbol library (``symbols/pvsld-symbols-cfe.dxf``, see
:mod:`pvsld.symbols.cfe.cli`).
Findings are printed in Spanish, as the reviewers read them; the CLI itself speaks English.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

import yaml

from pvsld import __version__
from pvsld.catalogue import ComponentRegistry, UnknownComponentError
from pvsld.catalogue import cli as catalogue_cli
from pvsld.catalogue.errors import CatalogueError
from pvsld.core.policy import DEFAULT_DC_AC_ERROR_ABOVE, DEFAULT_DC_AC_WARN_ABOVE, DcAcPolicy
from pvsld.core.rules import Finding
from pvsld.core.validation import ValidationReport
from pvsld.finishers.core_console import (
    DEFAULT_LAYOUT,
    DEFAULT_PLOTTER,
    DEFAULT_TIMEOUT_S,
    FinisherError,
    FinishOptions,
    FinishResult,
    finish,
)
from pvsld.service import (
    GenerationResult,
    SpecFileError,
    generate_single_line_diagram,
    load_spec_file,
    validate_pv_design,
)
from pvsld.sizing import SizingInputError, format_report, load_request, size_pv_system
from pvsld.symbols.cfe import cli as symbols_cli


def _finding_line(finding: Finding) -> str:
    return (
        f"[{finding.severity.value}] {finding.rule_id} {finding.subject}: {finding.message_es} "
        f"({', '.join(finding.mx_ids)})"
    )


def _print_findings(report: ValidationReport, stream: object) -> None:
    for finding in report.findings:
        print(_finding_line(finding), file=stream)  # type: ignore[call-overload]


def _summary(report: ValidationReport) -> str:
    return f"{len(report.errors)} errors, {len(report.warnings)} warnings"


def _validate(args: argparse.Namespace) -> int:
    try:
        data = load_spec_file(args.path)
    except SpecFileError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    try:
        policy = DcAcPolicy(warn_above=args.dc_ac_warn, error_above=args.dc_ac_error)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    report = validate_pv_design(data, dc_ac_policy=policy)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.ok else 1
    if report.ok:
        derived = report.derived
        assert derived is not None  # a valid report always carries the derived values
        print(
            f"OK: {args.path} passes {report.rulepack} ({_summary(report)}); "
            f"{derived.kwp_total:.2f} kWp DC, {derived.kwac_total:.2f} kWac"
        )
        _print_findings(report, sys.stdout)
        return 0
    print(f"FAILED: {args.path} violates {report.rulepack} ({_summary(report)})", file=sys.stderr)
    _print_findings(report, sys.stderr)
    return 1


def _write_spec(path: Path, spec: dict[str, object]) -> None:
    """Write the specification as JSON (``.json``) or YAML (anything else)."""
    if path.suffix.lower() == ".json":
        text = json.dumps(spec, ensure_ascii=False, indent=2) + "\n"
    else:
        text = yaml.safe_dump(spec, allow_unicode=True, sort_keys=False)
    path.write_text(text, encoding="utf-8")


def _size(args: argparse.Namespace) -> int:
    try:
        request = load_request(args.path)
        registry = ComponentRegistry.load(
            args.catalogue, include_unreviewed=args.include_unreviewed
        )
        result = size_pv_system(request, registry)
    except (CatalogueError, SizingInputError, UnknownComponentError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    data = result.to_dict()
    if args.output is not None and result.spec is not None:
        try:
            _write_spec(args.output, data["selected"]["spec"])
        except OSError as error:
            print(f"error: cannot write {args.output}: {error}", file=sys.stderr)
            return 1
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0 if result.ok else 1
    notes = []
    if registry.skipped_unreviewed:
        notes.append(f"skipped unreviewed records: {', '.join(registry.skipped_unreviewed)}")
    if args.include_unreviewed:
        notes.append(
            "WARNING: records the owner has not reviewed may be in use (--include-unreviewed)"
        )
    text = "\n".join([format_report(result), *notes])
    if args.output is not None and result.spec is not None:
        text += f"\nwrote {args.output}"
    print(text, file=sys.stdout if result.ok else sys.stderr)
    return 0 if result.ok else 1


def _describe(result: GenerationResult) -> str:
    assert result.dxf_path is not None
    assert result.readback is not None
    readback = result.readback
    lines = [
        f"{'OK' if result.ok else 'FAILED'}: wrote {result.dxf_path} "
        f"({(result.size_bytes or 0) / 1024:.0f} KiB, sha256 {result.sha256})",
    ]
    if result.png_path is not None:
        lines.append(f"preview: {result.png_path}")
    lines.append(
        f"read-back: audit {readback.audit_errors} errors / {readback.audit_fixes} fixes; "
        f"attributes {readback.attributes_matched}/{readback.attributes_checked}; "
        f"dangling ports {len(readback.dangling_ports)}; "
        f"entities on layer 0: {readback.layer_zero_entities}"
    )
    lines += [f"problem: {problem}" for problem in readback.problems]
    lines.append(
        "timings (ms): "
        + ", ".join(f"{name} {value:g}" for name, value in result.timings_ms.items())
    )
    return "\n".join(lines)


def _generate(args: argparse.Namespace) -> int:
    try:
        data = load_spec_file(args.path)
    except SpecFileError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    try:
        result = generate_single_line_diagram(data, args.output, png=args.png)
    except OSError as error:
        print(f"error: cannot write {args.output}: {error}", file=sys.stderr)
        return 1
    if result.dxf_path is None:
        print(
            f"FAILED: {args.path} violates {result.validation.rulepack} "
            f"({_summary(result.validation)}); nothing was written",
            file=sys.stderr,
        )
        _print_findings(result.validation, sys.stderr)
        return 1
    print(_describe(result), file=sys.stdout if result.ok else sys.stderr)
    return 0 if result.ok else 1


def _describe_finish(result: FinishResult) -> str:
    duration = "n/a" if result.duration_s is None else f"{result.duration_s:.1f} s"
    lines = [
        f"{'OK' if result.ok else 'FAILED'}: Core Console finished {result.source.name} "
        f"in {duration}"
    ]
    if result.dwg is not None:
        trusted = "TrustedDWG text present" if result.dwg.trusted else "no TrustedDWG text"
        lines.append(
            f"dwg: {result.dwg.path} ({result.dwg.version}, {result.dwg.release}; {trusted})"
        )
    if result.pdf is not None:
        sizes = ", ".join(f"{w:g} x {h:g} mm" for w, h in result.pdf.page_sizes_mm[:1])
        lines.append(
            f"pdf: {result.pdf.path} ({result.pdf.pages} page(s){'; ' + sizes if sizes else ''})"
        )
    audit = result.audit
    lines.append(
        "audit: not found"
        if audit is None
        else f"audit: {audit.errors_found} errors found, {audit.errors_fixed} fixed"
    )
    if result.step_ms:
        lines.append(
            "steps (ms): "
            + ", ".join(f"{name} {value:g}" for name, value in result.step_ms.items())
        )
    lines.append(f"log: {result.paths.log}")
    lines += [f"problem: {problem}" for problem in result.problems]
    return "\n".join(lines)


def _finish(args: argparse.Namespace) -> int:
    options = FinishOptions(
        dwg=not args.no_dwg,
        pdf=not args.no_pdf,
        layout=args.layout,
        plotter=args.plotter,
        paper=args.paper,
        audit_fix=args.audit_fix,
        isolate=not args.no_isolate,
        timeout_s=args.timeout,
        overwrite=args.overwrite,
    )
    try:
        result = finish(args.path, args.out_dir, options=options, accoreconsole=args.accoreconsole)
    except (FinisherError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(_describe_finish(result), file=sys.stdout if result.ok else sys.stderr)
    return 0 if result.ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pvsld",
        description="Generate Mexican photovoltaic single-line diagrams (DXF first).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser(
        "validate",
        help="validate a parameter file against the schema and the rule pack",
        description=(
            "Parse a PV system specification (YAML or JSON) against the parameter model and run "
            "the rule pack mx-gd-2026.10. Exit code 1 when an error-severity rule fails."
        ),
    )
    validate.add_argument("path", type=Path, metavar="PATH", help="parameter YAML or JSON file")
    validate.add_argument("--json", action="store_true", help="print the report as JSON")
    validate.add_argument(
        "--dc-ac-warn",
        type=float,
        default=DEFAULT_DC_AC_WARN_ABOVE,
        metavar="RATIO",
        help=f"STR-007: warn above this DC/AC ratio (default {DEFAULT_DC_AC_WARN_ABOVE:g})",
    )
    validate.add_argument(
        "--dc-ac-error",
        type=float,
        default=DEFAULT_DC_AC_ERROR_ABOVE,
        metavar="RATIO",
        help=f"STR-007: fail above this DC/AC ratio (default {DEFAULT_DC_AC_ERROR_ABOVE:g})",
    )
    validate.set_defaults(run=_validate)

    generate = subcommands.add_parser(
        "generate",
        help="validate and render the A3 single-line diagram as DXF R2018",
        description=(
            "Validate the specification, write the DXF sheet and verify it by reading it back. "
            "Nothing is written when validation fails."
        ),
    )
    generate.add_argument("path", type=Path, metavar="PATH", help="parameter YAML or JSON file")
    generate.add_argument(
        "-o", "--output", type=Path, required=True, metavar="OUT.dxf", help="DXF file to write"
    )
    generate.add_argument(
        "--png", action="store_true", help="also write a PNG preview next to the DXF"
    )
    generate.set_defaults(run=_generate)

    finish_cmd = subcommands.add_parser(
        "finish",
        help="convert a DXF to DWG 2018 and a PDF with the local AutoCAD Core Console",
        description=(
            "Run accoreconsole.exe (Windows, licensed full AutoCAD) on one drawing: AUDIT, save "
            "DWG 2018, plot the layout to PDF. Exit code 1 unless every output was produced and "
            "checked; a run without a usable licence is reported, never silently accepted."
        ),
    )
    finish_cmd.add_argument("path", type=Path, metavar="DRAWING", help="DXF (or DWG) to finish")
    finish_cmd.add_argument(
        "-d",
        "--out-dir",
        type=Path,
        default=None,
        metavar="DIR",
        help="folder for the DWG, PDF, script and log (default: next to the drawing)",
    )
    finish_cmd.add_argument(
        "--accoreconsole",
        type=Path,
        default=None,
        metavar="EXE",
        help="path of accoreconsole.exe (default: $PVSLD_ACCORECONSOLE, then the newest AutoCAD)",
    )
    finish_cmd.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_S,
        metavar="SECONDS",
        help=f"stop the Core Console process after this many seconds ({DEFAULT_TIMEOUT_S:g})",
    )
    finish_cmd.add_argument("--no-dwg", action="store_true", help="do not save a DWG")
    finish_cmd.add_argument("--no-pdf", action="store_true", help="do not plot a PDF")
    finish_cmd.add_argument(
        "--layout", default=DEFAULT_LAYOUT, help=f"layout to plot (default {DEFAULT_LAYOUT})"
    )
    finish_cmd.add_argument(
        "--plotter", default=DEFAULT_PLOTTER, help=f"PC3 for the PDF (default {DEFAULT_PLOTTER!r})"
    )
    finish_cmd.add_argument(
        "--paper",
        default=None,
        metavar="MEDIA",
        help="plot with this paper size instead of the layout's page setup",
    )
    finish_cmd.add_argument(
        "--audit-fix", action="store_true", help="let AUDIT fix errors (it always reports them)"
    )
    finish_cmd.add_argument(
        "--no-isolate",
        action="store_true",
        help="use the AutoCAD user profile instead of a private /isolate folder",
    )
    finish_cmd.add_argument(
        "--overwrite", action="store_true", help="replace a DWG or PDF from an earlier run"
    )
    finish_cmd.add_argument("--json", action="store_true", help="print the result as JSON")
    finish_cmd.set_defaults(run=_finish)

    size = subcommands.add_parser(
        "size",
        help="size strings, protection and conductors from the catalogue (Stage 3.4)",
        description=(
            "Read a sizing request (YAML or JSON: module, inverters, target, template; see "
            "examples/sizing_jinko_growatt.yaml), enumerate the string configurations, reject "
            "those that break a rule, rank the rest and print the selection. Exit code 1 when no "
            "configuration survives."
        ),
    )
    size.add_argument("path", type=Path, metavar="REQUEST", help="sizing request YAML or JSON file")
    size.add_argument(
        "--catalogue",
        type=Path,
        default=catalogue_cli.DEFAULT_RECORDS,
        metavar="DIR",
        help="component records folder (default datasheets/records)",
    )
    size.add_argument(
        "--include-unreviewed",
        action="store_true",
        help="also use records the owner has not reviewed (development only)",
    )
    size.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        metavar="SPEC",
        help="write the selected parameter specification (.yaml or .json)",
    )
    size.add_argument("--json", action="store_true", help="print the full result as JSON")
    size.set_defaults(run=_size)
    catalogue_cli.register(subcommands)
    symbols_cli.register(subcommands)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the ``pvsld`` console script; returns the process exit code."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
    args = build_parser().parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
