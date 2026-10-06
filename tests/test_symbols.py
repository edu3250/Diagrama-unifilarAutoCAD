"""The symbol catalogue is a consistent, self-describing library (ADR-0003)."""

from __future__ import annotations

import json
import math
import re
from itertools import pairwise

import pytest

from pvsld.core import layers
from pvsld.symbols import (
    APP_ID,
    BLOCK_PREFIX,
    LIBRARY_VERSION,
    SYMBOLS,
    get_symbol,
    symbol_catalogue,
)
from pvsld.symbols.catalogue import (
    HIDDEN_ATTRIBUTES,
    TITLE_BLOCK_FIELDS,
    TITLE_BLOCK_HEIGHT_MM,
    TITLE_BLOCK_WIDTH_MM,
    Circle,
    Label,
    Line,
    Polyline,
    SymbolDef,
)

COMPONENTS = [s for s in SYMBOLS.values() if s.name != "PVSLD_TTLB"]
GRID_MM = 2.5
TOLERANCE_MM = 0.01


def _segments(symbol: SymbolDef) -> list[tuple[float, float, float, float]]:
    segments = []
    for item in symbol.geometry:
        if isinstance(item, Line):
            segments.append((item.x1, item.y1, item.x2, item.y2))
        elif isinstance(item, Polyline):
            points = list(item.points)
            pairs = list(pairwise(points))
            if item.closed:
                pairs.append((points[-1], points[0]))
            segments += [(a[0], a[1], b[0], b[1]) for a, b in pairs]
    return segments


def _distance_to_segment(px: float, py: float, seg: tuple[float, float, float, float]) -> float:
    x1, y1, x2, y2 = seg
    dx, dy = x2 - x1, y2 - y1
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / length_sq))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def test_library_identity() -> None:
    assert BLOCK_PREFIX == "PVSLD_"
    assert APP_ID == "PVSLD"
    assert re.fullmatch(r"\d+\.\d+\.\d+", LIBRARY_VERSION)


def test_block_names_use_the_adr_0003_prefix_and_are_unique() -> None:
    names = [s.name for s in SYMBOLS.values()]
    assert all(name.startswith(BLOCK_PREFIX) for name in names)
    assert len(set(names)) == len(names)
    assert all(re.fullmatch(r"[A-Z0-9_]+", name) for name in names)


def test_get_symbol_rejects_unknown_names() -> None:
    assert get_symbol("PVSLD_CB").function == "Interruptor termomagnético"
    with pytest.raises(KeyError, match="PVSLD_NOPE"):
        get_symbol("PVSLD_NOPE")


@pytest.mark.parametrize("symbol", SYMBOLS.values(), ids=lambda s: s.name)
def test_attribute_tags_are_uppercase_ascii_and_unique(symbol: SymbolDef) -> None:
    assert len(set(symbol.tags)) == len(symbol.tags)
    assert all(re.fullmatch(r"[A-Z][A-Z0-9_]*", tag) for tag in symbol.tags)


@pytest.mark.parametrize("symbol", SYMBOLS.values(), ids=lambda s: s.name)
def test_every_symbol_carries_the_hidden_identity_attributes(symbol: SymbolDef) -> None:
    by_tag = {a.tag: a for a in symbol.attdefs}
    for tag in HIDDEN_ATTRIBUTES:
        assert tag in by_tag, f"{symbol.name} lacks {tag}"
        assert not by_tag[tag].visible
    assert "TAG" in by_tag
    assert "DESC" in by_tag


@pytest.mark.parametrize("symbol", COMPONENTS, ids=lambda s: s.name)
def test_components_show_their_tag_and_description(symbol: SymbolDef) -> None:
    by_tag = {a.tag: a for a in symbol.attdefs}
    assert by_tag["TAG"].visible
    assert by_tag["DESC"].visible


@pytest.mark.parametrize("symbol", COMPONENTS, ids=lambda s: s.name)
def test_ports_are_on_the_grid_and_have_unique_ids(symbol: SymbolDef) -> None:
    assert symbol.ports, "a component needs at least one port"
    assert len({p.id for p in symbol.ports}) == len(symbol.ports)
    for port in symbol.ports:
        assert port.x % GRID_MM == 0, f"{symbol.name}.{port.id} x={port.x} is off the grid"
        assert port.y % GRID_MM == 0, f"{symbol.name}.{port.id} y={port.y} is off the grid"


@pytest.mark.parametrize("symbol", COMPONENTS, ids=lambda s: s.name)
def test_every_port_touches_the_symbol_geometry(symbol: SymbolDef) -> None:
    segments = _segments(symbol)
    circles = [c for c in symbol.geometry if isinstance(c, Circle)]
    for port in symbol.ports:
        on_segment = any(_distance_to_segment(port.x, port.y, s) <= TOLERANCE_MM for s in segments)
        on_circle = any(
            abs(math.hypot(port.x - c.cx, port.y - c.cy) - c.radius) <= TOLERANCE_MM
            for c in circles
        )
        assert on_segment or on_circle, f"{symbol.name}.{port.id} floats off the geometry"


def test_port_kinds_and_directions_are_declared() -> None:
    inverter = get_symbol("PVSLD_INV")
    assert [(p.id, p.kind, p.direction) for p in inverter.ports] == [
        ("A", "DC", "left"),
        ("B", "DC", "left"),
        ("AC", "AC", "right"),
        ("PE", "PE", "down"),
    ]
    assert inverter.port("B").required is False
    assert inverter.port("A").required is True
    with pytest.raises(KeyError, match="NOPE"):
        inverter.port("NOPE")


@pytest.mark.parametrize("symbol", SYMBOLS.values(), ids=lambda s: s.name)
def test_geometry_uses_house_layers_and_never_layer_zero(symbol: SymbolDef) -> None:
    used = {symbol.layer}
    used |= {g.layer for g in symbol.geometry}
    used |= {a.layer for a in symbol.attdefs}
    assert "0" not in used
    assert used <= layers.LAYER_NAMES


def test_labels_inside_symbols_are_spanish_or_symbolic_and_legible() -> None:
    for symbol in SYMBOLS.values():
        for item in symbol.geometry:
            if isinstance(item, Label):
                assert item.height >= 2.5, f"{symbol.name}: text below 2.5 mm"


def test_equipment_symbols_expose_manufacturer_and_model() -> None:
    assert {"MFR", "MODEL"} <= set(get_symbol("PVSLD_INV").tags)
    assert {"MFR", "MODEL"} <= set(get_symbol("PVSLD_PV_STRING").tags)


def test_title_block_has_the_mexican_fields() -> None:
    tags = set(get_symbol("PVSLD_TTLB").tags)
    assert {
        "PROYECTO",
        "UBICACION",
        "RPU",
        "NUM_SERVICIO",
        "RESPONSABLE",
        "CEDULA",
        "FECHA",
        "PLANO_NO",
        "TITULO",
        "ESCALA",
        "REV",
        "NORMA",
    } <= tags


def test_title_block_fields_tile_their_rows_without_overlap() -> None:
    rows: dict[int, list[tuple[float, float]]] = {}
    for _tag, _caption, x0, x1, row, _height in TITLE_BLOCK_FIELDS:
        assert 0 <= x0 < x1 <= TITLE_BLOCK_WIDTH_MM
        rows.setdefault(row, []).append((x0, x1))
    assert max(rows) * 10 + 10 == TITLE_BLOCK_HEIGHT_MM
    for row, spans in rows.items():
        spans.sort()
        assert spans[0][0] == 0
        assert spans[-1][1] == TITLE_BLOCK_WIDTH_MM, f"row {row} does not reach the right edge"
        for (_, end), (start, _) in pairwise(spans):
            assert end == start, f"row {row} has a gap or overlap at x={end}"


def test_title_block_value_text_fits_inside_its_cell() -> None:
    for tag, _caption, x0, x1, _row, height in TITLE_BLOCK_FIELDS:
        assert height <= 3.5
        assert x1 - x0 >= 15, f"{tag} cell is too narrow"


def test_catalogue_is_plain_json_and_lists_ports_and_attributes() -> None:
    catalogue = symbol_catalogue()
    json.dumps(catalogue)
    inv = next(c for c in catalogue if c["block"] == "PVSLD_INV")
    assert inv["version"] == LIBRARY_VERSION
    assert {p["id"] for p in inv["ports"]} == {"A", "B", "AC", "PE"}  # type: ignore[union-attr]
    assert any(a["tag"] == "COMP_ID" for a in inv["attributes"])  # type: ignore[union-attr]
