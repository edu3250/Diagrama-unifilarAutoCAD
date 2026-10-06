"""Command-line interface of ``pvsld``.

Usage::

    pvsld --version
    pvsld validate examples/residential_7p7kwp.yaml [--json]
    pvsld generate examples/residential_7p7kwp.yaml -o out/sld.dxf [--png]

``validate`` parses the specification against the parameter model and runs the rule pack
``mx-gd-2026.10``; the exit code is 1 when a rule of severity ``E`` fails. ``generate`` validates
again, writes the DXF R2018 sheet (and a PNG preview with ``--png``) and verifies the written file.
Findings are printed in Spanish, as the reviewers read them; the CLI itself speaks English.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from pvsld import __version__
from pvsld.core.rules import Finding
from pvsld.core.validation import ValidationReport
from pvsld.service import (
    GenerationResult,
    SpecFileError,
    generate_single_line_diagram,
    load_spec_file,
    validate_pv_design,
)


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
    report = validate_pv_design(data)
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
