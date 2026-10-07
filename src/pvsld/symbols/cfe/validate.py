"""Validate a symbol library DXF against the canonical definitions and the ADR-0003/0005 rules.

:func:`validate_document` reads what is *in the file* (blocks, attribute definitions, XDATA, layers,
the ``Legend`` layout), not what the Python definitions say, so it also catches a hand edit in
AutoCAD. :func:`validate_file` adds the staleness check: the committed bytes must equal what the
definitions render today, so the DXF cannot drift from its canonical source.

A problem is a short English sentence that names the block. An empty list means the file is valid.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf import path as ezpath
from ezdxf.document import Drawing
from ezdxf.layouts import BlockLayout
from ezdxf.lldxf import const
from ezdxf.lldxf.const import DXFError

from pvsld.backends.dxf import BLOCK_FORMAT
from pvsld.core import layers
from pvsld.symbols.cfe.build import (
    LEGEND_COLUMNS,
    LEGEND_LAYOUT,
    LEGEND_TITLE,
    block_xdata,
    legend_layout_name,
    legend_pages,
    render_library,
)
from pvsld.symbols.cfe.definitions import LIBRARY
from pvsld.symbols.cfe.model import (
    APP_ID,
    BLOCK_PREFIX,
    HIDDEN_TAGS,
    LIBRARY_VERSION,
    SOURCE_PREFIXES,
    SymbolSpec,
)

PORT_TOLERANCE_MM = 0.01
OUTLINE_TYPES = frozenset({"LINE", "LWPOLYLINE", "CIRCLE", "ARC"})
REGENERATE = "pvsld symbols build"


def _xdata(block: BlockLayout) -> list[tuple[int, Any]]:
    try:
        return [(tag.code, tag.value) for tag in block.block_record.get_xdata(APP_ID)]
    except DXFError:
        return []


def _flatten(entity: Any) -> list[tuple[float, float]]:
    return [(v.x, v.y) for v in ezpath.make_path(entity).flattening(0.005)]


def _distance_to_polyline(x: float, y: float, points: list[tuple[float, float]]) -> float:
    best = math.inf
    for (ax, ay), (bx, by) in pairwise(points):
        dx, dy = bx - ax, by - ay
        length_sq = dx * dx + dy * dy
        t = (
            0.0
            if length_sq == 0
            else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / length_sq))
        )
        best = min(best, math.hypot(x - (ax + t * dx), y - (ay + t * dy)))
    return best


def _port_distance(block: BlockLayout, x: float, y: float) -> float:
    return min(
        (_distance_to_polyline(x, y, _flatten(e)) for e in block if e.dxftype() in OUTLINE_TYPES),
        default=math.inf,
    )


def _check_block(doc: Drawing, spec: SymbolSpec) -> Iterable[str]:
    name = spec.name
    if name not in doc.blocks:
        yield f"{name}: block is missing"
        return
    block = doc.blocks.get(name)

    attdefs = [e for e in block if e.dxftype() == "ATTDEF"]
    tags = [e.dxf.tag for e in attdefs]
    if tags != list(spec.tags):
        yield f"{name}: attribute tags {tags} differ from the definition {list(spec.tags)}"
    for attdef in attdefs:
        hidden = bool(attdef.dxf.flags & const.ATTRIB_INVISIBLE)
        if attdef.dxf.tag in HIDDEN_TAGS and not hidden:
            yield f"{name}: attribute {attdef.dxf.tag} must be hidden"
        if attdef.dxf.tag == "SOURCE_STANDARD" and attdef.dxf.text != spec.source:
            yield f"{name}: SOURCE_STANDARD default {attdef.dxf.text!r} != {spec.source!r}"

    if not spec.source.startswith(SOURCE_PREFIXES):
        yield f"{name}: source {spec.source!r} names no known standard"

    for entity in block:
        layer = entity.dxf.layer
        if layer == layers.OVERALL_VIEWPORT:
            yield f"{name}: {entity.dxftype()} on layer 0"
        elif layer not in layers.LAYER_NAMES:
            yield f"{name}: {entity.dxftype()} on layer {layer!r}, not in the house standard"

    tags_x = _xdata(block)
    if not tags_x:
        yield f"{name}: block record has no {APP_ID} XDATA"
        return
    if tags_x[0] != (1000, BLOCK_FORMAT):
        yield f"{name}: XDATA does not start with {BLOCK_FORMAT!r}"
    elif tags_x[1] != (1000, LIBRARY_VERSION):
        yield f"{name}: library version {tags_x[1][1]!r} is not {LIBRARY_VERSION!r}"
    elif tags_x != block_xdata(spec):
        yield f"{name}: XDATA (ports or source) differs from the definition"
    for port in spec.ports:
        distance = _port_distance(block, port.x, port.y)
        if distance > PORT_TOLERANCE_MM:
            yield f"{name}: port {port.id} is {distance:.3f} mm off the symbol outline"


def _check_legend(doc: Drawing, specs: tuple[SymbolSpec, ...]) -> Iterable[str]:
    names = [n for n in doc.layouts.names() if n.startswith(LEGEND_LAYOUT)]
    if LEGEND_LAYOUT not in names:
        yield f"layout {LEGEND_LAYOUT!r} is missing"
        return
    expected = [legend_layout_name(i) for i in range(1, len(legend_pages(specs)) + 1)]
    if sorted(names) != sorted(expected):
        yield f"the Legend layouts are {sorted(names)}, expected {sorted(expected)}"
    inserted: list[str] = []
    for name in names:
        legend = doc.layouts.get(name)
        inserted += [e.dxf.name for e in legend.query("INSERT")]
        texts = [e.dxf.text for e in legend.query("TEXT")]
        if LEGEND_TITLE not in texts:
            yield f"{name}: the Legend has no title"
        if not any(f"v{LIBRARY_VERSION}" in text for text in texts):
            yield f"{name}: the Legend does not state the library version v{LIBRARY_VERSION}"
        for column in LEGEND_COLUMNS:
            if column not in texts:
                yield f"{name}: the Legend has no column {column!r}"
    if sorted(inserted) != sorted(spec.name for spec in specs):
        yield "the Legend does not insert every block exactly once"
    for name in inserted:
        if name not in doc.blocks:
            yield f"the Legend inserts the unknown block {name}"


def validate_document(doc: Drawing, specs: Iterable[SymbolSpec] = LIBRARY) -> list[str]:
    """Problems found in ``doc`` (empty when it is a valid symbol library)."""
    chosen = tuple(specs)
    problems: list[str] = []
    auditor = doc.audit()
    problems += [f"audit error: {error.message}" for error in auditor.errors]
    problems += [f"audit fix: {fix.message}" for fix in auditor.fixes]
    for spec in chosen:
        problems += _check_block(doc, spec)
    expected = {spec.name for spec in chosen}
    for block in doc.blocks:
        if block.name.startswith(BLOCK_PREFIX) and block.name not in expected:
            problems.append(f"{block.name}: block is not in the definitions")
    problems += _check_legend(doc, chosen)
    return problems


def validate_file(path: Path, *, check_fresh: bool = True) -> list[str]:
    """Validate the DXF at ``path``; with ``check_fresh`` it must equal the rendered definitions."""
    try:
        data = path.read_bytes()
    except OSError as error:
        return [f"cannot read {path}: {error.strerror or error}"]
    try:
        doc = ezdxf.readfile(path)
    except (OSError, DXFError) as error:
        return [f"{path} is not a readable DXF: {error}"]
    problems = validate_document(doc)
    if check_fresh and data != render_library():
        problems.append(f"{path} is stale: it differs from the definitions; run `{REGENERATE}`")
    return problems
