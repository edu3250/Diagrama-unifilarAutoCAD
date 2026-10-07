"""Shared helpers of the catalogue tests: the committed records as raw dicts, copies in tmp_path."""

from __future__ import annotations

import copy
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

RECORDS = Path(__file__).resolve().parents[1] / "datasheets" / "records"
MODULE = "modules/jinko-jkm-66hl4m-bdv.yaml"
INVERTER = "inverters/huawei-sun2000-ktl-l1.yaml"
BREAKER = "protection/schneider-acti9-c60pv-dc.yaml"
ET_MODULE = "modules/etsolar-et-m672bh.yaml"
GROWATT = "inverters/growatt-min-tl-x2.yaml"
SUNTREE = "protection/suntree-sl7n-63.yaml"
ALL_RECORDS = (MODULE, ET_MODULE, INVERTER, GROWATT, BREAKER, SUNTREE)

Mutation = Callable[[dict[str, Any]], None]


def raw(relative: str) -> dict[str, Any]:
    """The committed record as a plain dict (a fresh copy every call)."""
    data = yaml.safe_load((RECORDS / relative).read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return copy.deepcopy(data)


def write(root: Path, relative: str, data: dict[str, Any]) -> Path:
    """Write ``data`` as ``root/relative`` (creating folders) and return the path."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def mark_reviewed(data: dict[str, Any], owner: str = "Test Owner") -> dict[str, Any]:
    """Set the review fields, as the owner does after comparing the record with the datasheet."""
    data["source"]["reviewed_by"] = owner
    data["source"]["review_date"] = "2026-10-08"
    return data


def copy_records(root: Path, *, reviewed: bool = False) -> Path:
    """Copy the committed records into ``root`` keeping their folder layout."""
    for relative in ALL_RECORDS:
        data = raw(relative)
        write(root, relative, mark_reviewed(data) if reviewed else data)
    return root
