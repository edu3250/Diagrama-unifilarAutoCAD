"""Canonical definitions of the CFE symbol library: names, sources, attributes, ports, layers."""

from __future__ import annotations

import re

import pytest

from pvsld.core import layers
from pvsld.symbols import SYMBOLS as PHASE2_SYMBOLS
from pvsld.symbols.cfe import LIBRARY, SYMBOLS, get_symbol
from pvsld.symbols.cfe.model import (
    COMMON_TAGS,
    GRID_MM,
    HIDDEN_TAGS,
    SOURCE_CFE_C,
    SOURCE_CFE_D,
    SOURCE_PREFIXES,
    Dot,
    Label,
    port_distance,
)

APPENDIX_C_BLOCKS = {
    "modulo_fotovoltaico": "PVSLD_PV_MODULE",
    "varistor": "PVSLD_SPD",
    "interruptor_termomagnetico": "PVSLD_CB",
    "inversor": "PVSLD_INV",
    "medidor_energia": "PVSLD_METER",
    "red_distribucion": "PVSLD_GRID",
    "gabinete_estructura": "PVSLD_ENCLOSURE",
    "diodo_paso": "PVSLD_DIODE",
    "cargas_iluminacion": "PVSLD_LOAD_LIGHT",
    "sensor_corriente": "PVSLD_CT",
    "interruptor_manual": "PVSLD_SWITCH",
    "transformador_aislamiento": "PVSLD_XFMR_ISO",
    "carga_contactos": "PVSLD_LOAD_RECEPT",
}


def test_the_library_has_one_block_per_name() -> None:
    names = [spec.name for spec in LIBRARY]
    assert len(names) == len(set(names))
    assert set(SYMBOLS) == set(names)


def test_every_name_follows_the_adr_0003_scheme() -> None:
    for name in SYMBOLS:
        assert re.fullmatch(r"PVSLD_[A-Z0-9_]+", name), name


def test_the_thirteen_appendix_c_symbols_are_present_and_sourced_to_appendix_c() -> None:
    assert len(APPENDIX_C_BLOCKS) == 13
    for block in APPENDIX_C_BLOCKS.values():
        assert get_symbol(block).source == SOURCE_CFE_C, block


def test_the_library_also_has_the_symbols_the_generator_needs() -> None:
    for name in (
        "PVSLD_GND",
        "PVSLD_COND_MARK",
        "PVSLD_POL_POS",
        "PVSLD_POL_NEG",
        "PVSLD_PV_STRING",
        "PVSLD_PI",
        "PVSLD_PANEL",
        "PVSLD_TTLB",
    ):
        assert name in SYMBOLS
    assert get_symbol("PVSLD_GND").source == SOURCE_CFE_D
    assert len(SYMBOLS) >= 17


def test_get_symbol_rejects_an_unknown_block() -> None:
    with pytest.raises(KeyError, match="unknown symbol"):
        get_symbol("PVSLD_NOPE")


@pytest.mark.parametrize("spec", LIBRARY, ids=lambda s: s.name)
def test_every_block_records_a_known_source_and_a_spanish_designation(spec) -> None:  # type: ignore[no-untyped-def]
    assert spec.source.startswith(SOURCE_PREFIXES)
    assert spec.description_es.strip()
    assert spec.note.strip()


@pytest.mark.parametrize("spec", LIBRARY, ids=lambda s: s.name)
def test_every_block_has_the_common_attributes_and_hides_the_identity_ones(spec) -> None:  # type: ignore[no-untyped-def]
    assert set(COMMON_TAGS) <= set(spec.tags)
    by_tag = {a.tag: a for a in spec.attdefs}
    for tag in HIDDEN_TAGS:
        assert not by_tag[tag].visible, tag
    assert len(spec.tags) == len(set(spec.tags)), "duplicate attribute tag"
    assert by_tag["SOURCE_STANDARD"].default == spec.source
    assert by_tag["DESC"].default == spec.description_es


@pytest.mark.parametrize("spec", LIBRARY, ids=lambda s: s.name)
def test_attribute_tags_are_uppercase_ascii_with_the_unit_in_the_tag(spec) -> None:  # type: ignore[no-untyped-def]
    for tag in spec.tags:
        assert re.fullmatch(r"[A-Z][A-Z0-9_]*", tag), tag


@pytest.mark.parametrize("spec", LIBRARY, ids=lambda s: s.name)
def test_no_entity_is_on_layer_zero_and_every_layer_is_in_the_house_standard(spec) -> None:  # type: ignore[no-untyped-def]
    used = {g.layer for g in spec.geometry} | {a.layer for a in spec.attdefs} | {spec.layer}
    assert "0" not in used
    assert used <= layers.LAYER_NAMES


@pytest.mark.parametrize("spec", LIBRARY, ids=lambda s: s.name)
def test_ports_are_unique_on_the_grid_and_touch_the_drawing(spec) -> None:  # type: ignore[no-untyped-def]
    ids = [p.id for p in spec.ports]
    assert len(ids) == len(set(ids))
    for port in spec.ports:
        assert port.x % GRID_MM == pytest.approx(0, abs=1e-6), (spec.name, port)
        assert port.y % GRID_MM == pytest.approx(0, abs=1e-6), (spec.name, port)
        assert port_distance(spec, port) < 0.01, (spec.name, port)


@pytest.mark.parametrize("spec", LIBRARY, ids=lambda s: s.name)
def test_every_block_has_geometry_and_sane_bounds(spec) -> None:  # type: ignore[no-untyped-def]
    assert spec.geometry
    x0, y0, x1, y1 = spec.bounds()
    assert x1 - x0 > 0 or y1 - y0 > 0
    assert max(x1 - x0, y1 - y0) < 200


def test_only_symbols_without_connections_have_no_ports() -> None:
    portless = {s.name for s in LIBRARY if not s.ports}
    assert portless == {
        "PVSLD_ENCLOSURE",
        "PVSLD_COND_MARK",
        "PVSLD_POL_POS",
        "PVSLD_POL_NEG",
        "PVSLD_JUNCTION",
        "PVSLD_TTLB",
    }


def test_the_inverter_drops_the_cert_attribute_and_keeps_the_rest() -> None:
    inverter = get_symbol("PVSLD_INV")
    assert "CERT" not in inverter.tags
    assert set(PHASE2_SYMBOLS["PVSLD_INV"].tags) - {"CERT"} <= set(inverter.tags)


@pytest.mark.parametrize("name", sorted(PHASE2_SYMBOLS))
def test_the_nine_phase_2_blocks_keep_their_tags_and_port_ids(name: str) -> None:
    old, new = PHASE2_SYMBOLS[name], get_symbol(name)
    assert set(old.tags) - {"CERT"} <= set(new.tags)
    assert {p.id for p in old.ports} <= {p.id for p in new.ports}
    for port in old.ports:
        assert new.port(port.id).kind == port.kind
        assert new.port(port.id).direction == port.direction
        assert new.port(port.id).required == port.required


def test_the_title_block_keeps_every_phase_2_field() -> None:
    assert set(PHASE2_SYMBOLS["PVSLD_TTLB"].tags) <= set(get_symbol("PVSLD_TTLB").tags)


def test_the_enclosures_use_the_dash_dot_layer_of_the_cfe_gabinete() -> None:
    enclosure = get_symbol("PVSLD_ENCLOSURE")
    assert enclosure.layer == layers.ENCLOSURES
    panel = get_symbol("PVSLD_PANEL")
    assert any(g.layer == layers.ENCLOSURES for g in panel.geometry)


def test_the_meter_carries_the_kwh_caption_and_the_inverter_the_a_b_markers() -> None:
    meter_text = [g.text for g in get_symbol("PVSLD_METER").geometry if isinstance(g, Label)]
    assert meter_text == ["kWh"]
    inverter_text = [g.text for g in get_symbol("PVSLD_INV").geometry if isinstance(g, Label)]
    assert inverter_text == ["A", "B"]


def test_the_string_is_built_from_two_cfe_modules_and_three_dots() -> None:
    string = get_symbol("PVSLD_PV_STRING")
    assert sum(isinstance(g, Dot) for g in string.geometry) == 3


def test_to_dict_lists_ports_and_attributes() -> None:
    data = get_symbol("PVSLD_CB").to_dict()
    assert data["block"] == "PVSLD_CB"
    assert data["source"] == SOURCE_CFE_C
    assert [p["id"] for p in data["ports"]] == ["IN", "OUT"]  # type: ignore[index, union-attr]
    assert any(a["tag"] == "COMP_ID" and not a["visible"] for a in data["attributes"])  # type: ignore[index, union-attr]
