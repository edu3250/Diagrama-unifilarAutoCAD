"""The symbol interface the generator uses: the CFE library (ADR-0005) behind ``pvsld.symbols``."""

from __future__ import annotations

import json
from itertools import pairwise

import pytest

from pvsld.symbols import (
    APP_ID,
    BLOCK_PREFIX,
    LIBRARY,
    LIBRARY_VERSION,
    SYMBOLS,
    combiner_name,
    get_symbol,
    symbol_catalogue,
)
from pvsld.symbols.cfe import definitions
from pvsld.symbols.cfe.definitions import (
    TITLE_BLOCK_FIELDS,
    TITLE_BLOCK_HEIGHT_MM,
    TITLE_BLOCK_WIDTH_MM,
)


def test_the_interface_is_the_cfe_library() -> None:
    assert (APP_ID, BLOCK_PREFIX) == ("PVSLD", "PVSLD_")
    assert SYMBOLS is definitions.SYMBOLS
    assert LIBRARY_VERSION == "0.6.0"
    assert get_symbol("PVSLD_CB") is definitions.BREAKER  # the CFE form (owner decision)


def test_get_symbol_resolves_a_combiner_for_any_supported_string_count() -> None:
    combiner = get_symbol(combiner_name(5))
    assert combiner.name == "PVSLD_COMBINER_5S"
    assert [p.id for p in combiner.ports if p.id.startswith("IN")] == [
        f"IN{i}" for i in range(1, 6)
    ]
    assert combiner_name(5) not in SYMBOLS  # defined on demand, not stored in the library file


@pytest.mark.parametrize(
    "name", ["PVSLD_NOPE", "PVSLD_COMBINER_0S", "PVSLD_COMBINER_25S", "PVSLD_COMBINER_05S"]
)
def test_get_symbol_rejects_unknown_names(name: str) -> None:
    with pytest.raises(KeyError, match="unknown symbol"):
        get_symbol(name)


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


def test_catalogue_is_plain_json_and_lists_every_block_with_ports_and_attributes() -> None:
    catalogue = symbol_catalogue()
    json.dumps(catalogue)
    assert [c["block"] for c in catalogue] == [spec.name for spec in LIBRARY]
    inv = next(c for c in catalogue if c["block"] == "PVSLD_INV")
    assert inv["version"] == LIBRARY_VERSION
    assert inv["source"] == "CFE G0100-04 Apéndice C"
    assert {p["id"] for p in inv["ports"]} == {"A", "B", "AC", "PE"}  # type: ignore[union-attr]
    assert any(a["tag"] == "COMP_ID" for a in inv["attributes"])  # type: ignore[union-attr]
