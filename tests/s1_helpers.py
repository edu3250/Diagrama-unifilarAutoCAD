"""Shared helpers for the Stage 2.1 (S1) tests: load the sample and derive mutated specs.

The sample is loaded as a plain mapping (what an MCP client would send), never as a model object,
so each test mutates its own deep copy and exercises the whole parse and validate path.
"""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "residential_7p7kwp.yaml"
GOLDEN_DIR = Path(__file__).resolve().parent / "golden"


def load_example() -> dict[str, Any]:
    """Return a fresh copy of the 7.70 kWp sample as a mapping."""
    loaded = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    assert isinstance(loaded, dict)
    return loaded


def mutated(change: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
    """Return a deep copy of the sample after applying ``change`` to it in place."""
    spec = copy.deepcopy(load_example())
    change(spec)
    return spec
