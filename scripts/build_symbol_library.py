"""Regenerate the CFE symbol library DXF (ADR-0005, Stage 4.2).

Usage (repository root, virtual environment active):

    python scripts/build_symbol_library.py                       # writes the library DXF
    python scripts/build_symbol_library.py --png out/legend.png  # also draws the Legend
    python scripts/build_symbol_library.py --check               # CI: exit 1 if stale

It is the same as ``pvsld symbols build``; the arguments are passed through. The output is
byte-identical on every run and platform.
"""

from __future__ import annotations

import sys

from pvsld.cli import main

if __name__ == "__main__":
    sys.exit(main(["symbols", "build", *sys.argv[1:]]))
