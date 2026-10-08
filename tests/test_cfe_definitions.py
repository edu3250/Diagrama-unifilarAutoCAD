"""Canonical definitions of the CFE symbol library: names, sources, attributes, ports, layers."""

from __future__ import annotations

import re
from dataclasses import replace

import pytest

from pvsld.core import layers
from pvsld.symbols import SYMBOLS as PHASE2_SYMBOLS
from pvsld.symbols.cfe import LIBRARY, SYMBOLS, get_symbol
from pvsld.symbols.cfe.definitions import (
    FAMILIES,
    MAX_COMBINER_STRINGS,
    combiner_box,
    combiner_name,
)
from pvsld.symbols.cfe.model import (
    COMMON_TAGS,
    GRID_MM,
    HIDDEN_TAGS,
    SOURCE_CFE_C,
    SOURCE_CFE_D,
    SOURCE_PREFIXES,
    Circle,
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
    assert len(SYMBOLS) == 57


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
        "PVSLD_BOUNDARY",
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


# --- Round 2: the components of the symbol map (owner decisions of 2026-10-08) ------------

NEW_BLOCKS = {
    "PVSLD_FUSE": "4.2.21",
    "PVSLD_DC_DISCONNECT": "Apéndice C",
    "PVSLD_FUSE_DISC": "4.2.176",
    "PVSLD_SAFETY_SWITCH": "4.2.128",
    "PVSLD_SPD_AC": "Apéndice C",
    "PVSLD_COMBINER": "composición",
    "PVSLD_GND_BUS": "4.2.130",
    "PVSLD_NEUTRAL_BUS": "4.2.129",
    "PVSLD_PE": "4.2.117",
    "PVSLD_GFDI": "fig. D1",
    "PVSLD_INS_MONITOR": "fig. D2",
    "PVSLD_AFCI": "composición",
    "PVSLD_BUSBAR": "Apéndice D",
    "PVSLD_TERMINAL": "4.2.140",
    "PVSLD_CROSSING": "4.2.12",
    "PVSLD_BOUNDARY": "composición",
    "PVSLD_METER_M": "4.2.126",
    "PVSLD_BATTERY": "4.2.280",
    "PVSLD_INV_HYBRID": "composición",
    "PVSLD_TRANSFER_SW": "07-71-03",
    "PVSLD_OPTIMIZER": "composición",
    "PVSLD_MICROINV": "composición",
    "PVSLD_CHARGE_CTRL": "composición",
    "PVSLD_MONITOR": "Apéndice D",
    "PVSLD_CONTACTOR": "4.2.168",
    "PVSLD_XFMR": "4.2.123",
    "PVSLD_CUTOUT": "4.2.122",
    "PVSLD_ARRESTER_MV": "4.2.178",
    "PVSLD_DISCONNECT_MV": "4.2.118",
    "PVSLD_CT_MV": "4.2.124",
    "PVSLD_VT_MV": "4.2.75",
    "PVSLD_RELAY": "07-73-01",
    "PVSLD_RCD": "UNE-EN 60617",
    "PVSLD_CB_IEC": "UNE-EN 60617",
    "PVSLD_FUSE_AC": "4.2.21",
}


def test_the_library_has_the_thirty_five_blocks_of_rounds_two_and_three() -> None:
    assert len(NEW_BLOCKS) == 35
    assert set(NEW_BLOCKS) <= set(SYMBOLS)


@pytest.mark.parametrize(("name", "reference"), sorted(NEW_BLOCKS.items()))
def test_every_new_block_cites_its_reference_in_the_source(name: str, reference: str) -> None:
    spec = get_symbol(name)
    assert reference in spec.source, spec.source
    assert spec.source.startswith(SOURCE_PREFIXES)


def test_nmx_blocks_also_record_their_nmx_clause_and_dge_blocks_say_dge() -> None:
    for name, spec in SYMBOLS.items():
        if spec.source.startswith("NMX-J-136-ANCE-2019"):
            assert "4.2." in spec.nmx_ref, name
        if "DGE" in spec.source:
            assert spec.source.startswith(("DGE (basada en IEC 60617)", "pvsld (composición)")), (
                name
            )


def test_compositions_without_an_official_symbol_are_labelled_as_such() -> None:
    for name in (
        "PVSLD_AFCI",
        "PVSLD_BOUNDARY",
        "PVSLD_INV_HYBRID",
        "PVSLD_OPTIMIZER",
        "PVSLD_MICROINV",
        "PVSLD_CHARGE_CTRL",
        "PVSLD_COMBINER",
    ):
        assert get_symbol(name).source.startswith("pvsld (composición)"), name


def test_the_dc_disconnect_reuses_the_cfe_switch_with_dc_ports_and_a_load_break_flag() -> None:
    switch, dc = get_symbol("PVSLD_SWITCH"), get_symbol("PVSLD_DC_DISCONNECT")
    assert [g.__class__ for g in dc.geometry] == [g.__class__ for g in switch.geometry]
    assert dc.layer == layers.DC_EQUIPMENT
    assert {p.kind for p in dc.ports} == {"DC"}
    assert "LOAD_BREAK" in dc.tags
    assert {p.id for p in dc.ports} == {p.id for p in switch.ports}


def test_the_two_thermomagnetic_breakers_share_attributes_and_ports() -> None:
    cfe, iec = get_symbol("PVSLD_CB"), get_symbol("PVSLD_CB_IEC")
    assert set(cfe.tags) <= set(iec.tags)
    assert [(p.id, p.kind, p.direction) for p in cfe.ports] == [
        (p.id, p.kind, p.direction) for p in iec.ports
    ]
    assert iec.source != cfe.source
    assert any(isinstance(g, Label) and g.text == "I>" for g in iec.geometry)


def test_the_export_meter_is_the_nmx_m_square_distinct_from_the_cfe_meter() -> None:
    cfe, nmx = get_symbol("PVSLD_METER"), get_symbol("PVSLD_METER_M")
    assert nmx.source.startswith("NMX-J-136-ANCE-2019 4.2.126")
    assert [g.text for g in nmx.geometry if isinstance(g, Label)] == ["M"]
    assert nmx.name != cfe.name


def test_the_protective_relay_carries_the_function_and_the_ansi_number_as_attributes() -> None:
    relay = get_symbol("PVSLD_RELAY")
    by_tag = {a.tag: a for a in relay.attdefs}
    assert by_tag["FUNCTION"].visible
    assert by_tag["ANSI_NO"].visible
    assert {p.kind for p in relay.ports} == {"SIG"}


def test_the_rcd_has_a_sensitivity_attribute_and_no_nmx_symbol() -> None:
    rcd = get_symbol("PVSLD_RCD")
    assert "IDN_MA" in rcd.tags
    assert "sin símbolo en NMX" in rcd.source


def test_every_symbol_belongs_to_a_known_family_and_families_are_contiguous() -> None:
    assert all(spec.family in FAMILIES for spec in LIBRARY)
    order = [spec.family for spec in LIBRARY]
    seen: list[str] = []
    for family in order:
        if not seen or seen[-1] != family:
            seen.append(family)
    assert seen == list(FAMILIES)


def test_port_kinds_are_dc_ac_pe_plus_signal_and_any() -> None:
    kinds = {p.kind for spec in LIBRARY for p in spec.ports}
    assert kinds == {"DC", "AC", "PE", "SIG", "ANY"}
    assert {p.kind for p in get_symbol("PVSLD_TERMINAL").ports} == {"ANY"}


def test_the_battery_marks_the_positive_plate_and_the_spd_has_an_ac_variant() -> None:
    battery = get_symbol("PVSLD_BATTERY")
    assert battery.port("POS").x > battery.port("NEG").x
    assert get_symbol("PVSLD_SPD_AC").port("L").kind == "AC"
    assert get_symbol("PVSLD_SPD").port("L").kind == "DC"


# --- Round 3: owner decisions on the v0.5.0 review (2026-10-08) ---------------------------


def test_the_ac_fuse_is_the_dc_fuse_shape_with_ac_ports() -> None:
    dc, ac = get_symbol("PVSLD_FUSE"), get_symbol("PVSLD_FUSE_AC")
    assert [(p.id, p.kind) for p in dc.ports] == [("IN", "DC"), ("OUT", "DC")]
    assert [(p.id, p.kind) for p in ac.ports] == [("IN", "AC"), ("OUT", "AC")]
    assert [replace(g, layer=ac.layer) for g in dc.geometry] == list(ac.geometry)
    assert ac.layer == layers.AC_EQUIPMENT
    assert dc.tags == ac.tags


@pytest.mark.parametrize("n", [1, 2, 3, 4, 8, MAX_COMBINER_STRINGS])
def test_the_combiner_has_one_breaker_and_one_input_per_string(n: int) -> None:
    spec = combiner_box(n)
    assert spec.name == combiner_name(n) == f"PVSLD_COMBINER_{n}S"
    inputs = [p for p in spec.ports if p.id.startswith("IN")]
    assert [p.id for p in inputs] == [f"IN{i}" for i in range(1, n + 1)]
    assert all(p.required and p.kind == "DC" for p in inputs)
    ys = [p.y for p in inputs]
    assert ys == sorted(ys, reverse=True)
    assert ys[0] == -ys[-1]  # symmetric about the output
    assert spec.port("OUT").y == 0
    breakers = [g for g in spec.geometry if isinstance(g, Circle)]
    assert len(breakers) == n
    for port in spec.ports:
        assert port.x % GRID_MM == 0
        assert port.y % GRID_MM == 0
        assert port_distance(spec, port) < 0.01
    _x0, y0, _x1, y1 = spec.bounds()
    assert y0 <= spec.port("PE").y
    assert y1 >= ys[0]
    default = {a.tag: a.default for a in spec.attdefs}["N_STRINGS"]
    assert default == str(n)


@pytest.mark.parametrize("n", [0, -1, MAX_COMBINER_STRINGS + 1])
def test_the_combiner_rejects_a_string_count_out_of_range(n: int) -> None:
    with pytest.raises(ValueError, match="strings"):
        combiner_box(n)


def test_the_library_combiner_is_the_two_string_form() -> None:
    library, two = get_symbol("PVSLD_COMBINER"), combiner_box(2)
    assert library.geometry == two.geometry
    assert library.ports == two.ports
    assert "PVSLD_COMBINER_<n>S" in library.note
