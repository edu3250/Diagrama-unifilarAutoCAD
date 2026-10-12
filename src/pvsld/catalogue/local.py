"""The user's local catalogue (Stage 3.6.3): equipment the bundled catalogue does not have.

A plugin user who needs a module, inverter or protection that is not in the catalogue adds it from
its datasheet: Claude reads the PDF, shows the values, and once the user confirms them
:func:`add_local_record` validates the record like any other, stamps its provenance (the PDF's
SHA-256, the user as reviewer) and writes it into the local folder. From then on
:func:`load_catalogue` merges it with the bundled records, so sizing, drawing and the project sheet
lists all see it.

The local folder (``$PVSLD_LOCAL_CATALOGUE_DIR``, default ``%APPDATA%\\pvsld\\catalogo`` on
Windows and ``~/.local/share/pvsld/catalogo`` elsewhere) has the layout of
``datasheets/records`` (``modules/``, ``inverters/``, ``protection/``, ``conductors/``) plus
``hojas_tecnicas/`` for the PDFs, which never leave the user's computer.

A broken or conflicting local record never breaks the catalogue: it is left out and reported in
``ComponentRegistry.local_problems``.
"""

from __future__ import annotations

import copy
import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml

from pvsld.catalogue.errors import CatalogueError
from pvsld.catalogue.registry import (
    RECORD_FOLDERS,
    ComponentRegistry,
    LoadedRecord,
    load_records,
    read_record,
    validate_family,
)

__all__ = [
    "DATASHEETS_FOLDER",
    "LOCAL_DIR_ENV",
    "LOCAL_REVIEWER",
    "LocalRecord",
    "add_local_record",
    "load_catalogue",
    "local_catalogue_dir",
]

LOCAL_DIR_ENV = "PVSLD_LOCAL_CATALOGUE_DIR"
DATASHEETS_FOLDER = "hojas_tecnicas"
LOCAL_REVIEWER = "usuario (catálogo local)"
DEFAULT_EXTRACTION = "pdf_text_layer"


def local_catalogue_dir(environ: Mapping[str, str] | None = None) -> Path:
    """``$PVSLD_LOCAL_CATALOGUE_DIR``, else the per-user data folder of this system."""
    env = os.environ if environ is None else environ
    configured = env.get(LOCAL_DIR_ENV, "").strip()
    if configured:
        return Path(configured).expanduser()
    if env.get("APPDATA"):
        return Path(env["APPDATA"]) / "pvsld" / "catalogo"
    data_home = env.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(data_home) / "pvsld" / "catalogo"


def _local_records(local: Path, bundled_ids: set[str]) -> tuple[list[LoadedRecord], list[str]]:
    """Valid local records that repeat no bundled component, and why the rest were left out."""
    records: list[LoadedRecord] = []
    problems: list[str] = []
    seen: set[str] = set()
    for file in sorted(local.rglob("*.yaml")):
        if DATASHEETS_FOLDER in file.relative_to(local).parts:
            continue
        try:
            family = read_record(file)
        except CatalogueError as error:
            problems += error.problems
            continue
        ids = {v.component_id for v in family.variants}
        clash = sorted(ids & (bundled_ids | seen))
        if clash:
            problems.append(f"{file}: left out, {', '.join(clash)} is already in the catalogue")
            continue
        seen |= ids
        records.append(LoadedRecord(file, family))
    return records, problems


def load_catalogue(
    bundled: Path | str,
    *,
    local: Path | None = None,
    include_unreviewed: bool = False,
) -> ComponentRegistry:
    """The bundled records (validated strictly) merged with the local catalogue, if it exists.

    Raises:
        CatalogueError: a bundled record is invalid (local problems are only reported).
    """
    records = load_records(bundled)
    if local is None or not local.is_dir():
        return ComponentRegistry.from_records(records, include_unreviewed=include_unreviewed)
    bundled_ids = {v.component_id for r in records for v in r.family.variants}
    local_records, problems = _local_records(local, bundled_ids)
    return ComponentRegistry.from_records(
        records,
        include_unreviewed=include_unreviewed,
        local_records=local_records,
        local_problems=problems,
    )


@dataclass(frozen=True)
class LocalRecord:
    """A record written into the local catalogue."""

    path: Path
    family_id: str
    component_type: str
    component_ids: tuple[str, ...]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def add_local_record(
    data: Mapping[str, Any],
    local: Path,
    *,
    datasheet: Path,
    registry: ComponentRegistry,
    reviewed_by: str = LOCAL_REVIEWER,
    today: date | None = None,
    overwrite: bool = False,
) -> LocalRecord:
    """Validate a record the user confirmed and write it into the local catalogue.

    ``data`` is the record as extracted from the datasheet, in the format of
    ``datasheets/records`` (see the example records). Its ``source`` only needs what was read
    (``title``, ``pages``, ``extraction_method``, ``notes``): the file name and SHA-256 come from
    ``datasheet``, and the user who confirmed the values is the reviewer.

    Raises:
        CatalogueError: the datasheet is missing, the record is invalid, or a component id is
            already in the catalogue (a local one may be replaced with ``overwrite``).
    """
    if not datasheet.is_file():
        raise CatalogueError([f"datasheet not found: {datasheet}"])
    day = today or date.today()
    record = copy.deepcopy(dict(data))
    source = dict(record.get("source") or {})
    record["source"] = {
        "filename": datasheet.name,
        "sha256": _sha256(datasheet),
        "title": source.get("title") or f"{record.get('manufacturer', '')} datasheet".strip(),
        "pages": source.get("pages") or [1],
        "extraction_method": source.get("extraction_method") or DEFAULT_EXTRACTION,
        "extraction_date": day,
        "reviewed_by": reviewed_by,
        "review_date": day,
        "notes": source.get("notes")
        or "Agregado al catálogo local; el usuario confirmó los valores contra la hoja técnica.",
    }
    family = validate_family(record)
    ids = tuple(v.component_id for v in family.variants)
    taken = [i for i in ids if i in registry and (not registry.is_local(i) or not overwrite)]
    if taken:
        where = "local catalogue" if all(registry.is_local(i) for i in taken) else "catalogue"
        raise CatalogueError(
            [
                f"{', '.join(taken)} is already in the {where}"
                + (
                    "; pass overwrite to replace the local record"
                    if where.startswith("local")
                    else ""
                )
            ]
        )
    target = local / RECORD_FOLDERS[family.component_type] / f"{family.family_id.lower()}.yaml"
    if target.exists() and not overwrite:
        raise CatalogueError([f"{target} already exists; pass overwrite to replace it"])
    target.parent.mkdir(parents=True, exist_ok=True)
    header = (
        f"# Local catalogue record, added {day.isoformat()} from {datasheet.name}.\n"
        "# The user confirmed every value against the datasheet; the PDF stays on this computer.\n"
    )
    body = yaml.safe_dump(record, allow_unicode=True, sort_keys=False, width=100)
    target.write_text(header + body, encoding="utf-8")
    read_record(target)  # what was written reads back as the same valid record
    return LocalRecord(target, family.family_id, family.component_type, ids)
