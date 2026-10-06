"""Command-line interface of ``pvsld``.

Usage::

    pvsld --version
    pvsld validate-example examples/residential_7p7kwp.yaml

``validate-example`` is a deliberately shallow smoke check for the sample parameter file: the YAML
must load and contain the top-level sections of the PV SLD parameter model. Real schema and
rule-pack validation arrives with the deterministic core in Stage 2.1.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import yaml

from pvsld import __version__

# Sections the parameter model (schema_version 0.1.0) requires for a low-voltage residential
# system. Optional or conditional sections (``monitoring``, and ``transformer`` and
# ``mt_protection`` for medium voltage) are accepted but not required.
REQUIRED_TOP_LEVEL_SECTIONS: tuple[str, ...] = (
    "schema_version",
    "project",
    "standards",
    "utility",
    "modules",
    "inverters",
    "strings",
    "dc_bos",
    "ac_bos",
    "circuits",
    "grounding",
    "storage",
    "title_block",
    "layout",
)


class ExampleError(ValueError):
    """The parameter file cannot be used; the message says why and is safe to show the user."""


def load_example(path: Path) -> dict[str, Any]:
    """Load ``path`` as YAML and check that it has every required top-level section.

    Raises:
        ExampleError: the file is missing, is not valid YAML, is not a mapping, or lacks sections.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ExampleError(f"file not found: {path}") from None
    except OSError as exc:
        raise ExampleError(f"cannot read {path}: {exc.strerror or exc}") from exc

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ExampleError(f"invalid YAML in {path}: {exc}") from exc

    if not isinstance(document, dict):
        raise ExampleError(
            f"{path} must contain a YAML mapping at the top level, found {type(document).__name__}"
        )

    missing = [name for name in REQUIRED_TOP_LEVEL_SECTIONS if name not in document]
    if missing:
        raise ExampleError(f"{path} is missing required top-level sections: {', '.join(missing)}")
    return document


def _validate_example(args: argparse.Namespace) -> int:
    path: Path = args.path
    try:
        document = load_example(path)
    except ExampleError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(
        f"OK: {path} loads and has all {len(REQUIRED_TOP_LEVEL_SECTIONS)} required top-level "
        f"sections (schema_version {document['schema_version']})"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pvsld",
        description="Generate Mexican photovoltaic single-line diagrams (DXF first).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser(
        "validate-example",
        help="check that a parameter YAML loads and has the expected top-level sections",
        description=(
            "Shallow smoke check only: the file must be valid YAML and contain the top-level "
            "sections of the PV SLD parameter model. Full validation arrives in Stage 2.1."
        ),
    )
    validate.add_argument("path", type=Path, metavar="PATH", help="parameter YAML file")
    validate.set_defaults(run=_validate_example)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Entry point of the ``pvsld`` console script; returns the process exit code."""
    args = build_parser().parse_args(argv)
    return int(args.run(args))


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
