"""Deterministic calculations reproduce the worked examples of the vault notes."""

from __future__ import annotations

import pytest

from pvsld.core import calc
from pvsld.core.model import PvSystemSpec, parse_spec
from pvsld.core.tables import NOM_001_SEDE_2012, get_tables
from s1_helpers import load_example, mutated


@pytest.fixture(scope="module")
def spec() -> PvSystemSpec:
    return parse_spec(load_example())


# --- Temperature-corrected Voc (vault: Temperature-Corrected Voc, worked example) -------------


def test_voc_coefficient_method_matches_the_worked_example(spec: PvSystemSpec) -> None:
    module = spec.modules[0]
    assert calc.voc_max_module_v(module, -3, "coefficient") == pytest.approx(53.35, abs=0.005)
    assert calc.voc_max_string_v(module, 7, -3, "coefficient") == pytest.approx(373.4, abs=0.05)
    # the vault rounds the module Voc to 53.35 V first, hence the wider tolerance (586.85 vs 586.9)
    assert calc.voc_max_string_v(module, 11, -3, "coefficient") == pytest.approx(586.9, abs=0.06)


def test_voc_table_and_iec_default_methods_match_the_worked_example(spec: PvSystemSpec) -> None:
    module = spec.modules[0]
    assert calc.voc_max_module_v(module, -3, "table_690_7") == pytest.approx(55.55, abs=0.005)
    assert calc.voc_max_string_v(module, 11, -3, "table_690_7") == pytest.approx(611.1, abs=0.05)
    assert calc.voc_max_module_v(module, -3, "iec_default_1_2") == pytest.approx(59.52, abs=0.005)


def test_coefficient_method_without_a_coefficient_is_an_error(spec: PvSystemSpec) -> None:
    module = spec.modules[0].model_copy(update={"beta_voc_pct_c": None})
    with pytest.raises(ValueError, match="beta_voc_pct_c"):
        calc.voc_max_module_v(module, -3, "coefficient")


@pytest.mark.parametrize(
    ("t_min_c", "factor"),
    [
        (24, 1.02),
        (20, 1.02),
        (19, 1.04),
        (0, 1.10),
        (-0.5, 1.12),
        (-5, 1.12),
        (-6, 1.14),
        (-40, 1.25),
    ],
)
def test_table_690_7_factor_rows(t_min_c: float, factor: float) -> None:
    assert calc.voc_factor_table_690_7(t_min_c) == factor


def test_table_690_7_is_neutral_at_and_above_25_c_and_rejects_below_minus_40() -> None:
    assert calc.voc_factor_table_690_7(25) == 1.0
    with pytest.raises(ValueError, match="-41"):
        calc.voc_factor_table_690_7(-41)


# --- String sizing (vault: PV String Sizing, worked example) ----------------------------------


def test_cell_temperature_and_hot_vmp_match_the_worked_example(spec: PvSystemSpec) -> None:
    module = spec.modules[0]
    assert calc.t_cell_max_c(38) == 73
    assert calc.vmp_module_v(module, 73) == pytest.approx(34.61, abs=0.005)
    assert calc.vmp_hot_string_v(module, 7, 38) == pytest.approx(242.3, abs=0.05)
    assert calc.vmp_cold_string_v(module, 7, -3) == pytest.approx(7 * 45.68, abs=0.05)


def test_string_limits_match_the_worked_example(spec: PvSystemSpec) -> None:
    limits = calc.string_limits(spec, spec.strings[0])
    assert limits.n_max == 11
    assert limits.n_min_operating == 3
    assert limits.n_min_full_power == 6


def test_dwelling_limit_caps_the_string_length_at_600_v() -> None:
    data = mutated(lambda s: s["inverters"][0].update({"vdc_max_v": 1000}))
    spec = parse_spec(data)
    assert calc.string_limits(spec, spec.strings[0]).n_max == 11  # 600 V NOM limit, not 1000 V


def test_short_circuit_input_current_uses_the_125_percent_factor(spec: PvSystemSpec) -> None:
    assert calc.isc_input_a(spec.modules[0].isc_a, 1) == pytest.approx(17.5)
    assert calc.isc_input_a(spec.modules[0].isc_a, 2) == pytest.approx(35.0)


# --- OCPD and conductors (vault: PV Conductor Sizing and Voltage Drop) ------------------------


@pytest.mark.parametrize(
    ("amps", "expected"), [(34.125, 35), (35, 35), (35.1, 40), (1, 15), (801, 1000), (0, 15)]
)
def test_next_standard_ocpd(amps: float, expected: float) -> None:
    assert calc.next_standard_ocpd_a(amps) == expected


def test_ocpd_minimum_is_125_percent_of_the_maximum_current() -> None:
    assert calc.ocpd_min_a(27.3) == pytest.approx(34.125)


def test_next_standard_ocpd_beyond_the_table_is_an_error() -> None:
    with pytest.raises(ValueError, match="7000"):
        calc.next_standard_ocpd_a(7000)


def test_conductor_ampacity_columns_follow_table_310_15_b_16() -> None:
    assert calc.ampacity_a("10 AWG", 75) == 35
    assert calc.ampacity_a("10 AWG", 90) == 40
    assert calc.ampacity_a("8 AWG", 75) == 50
    assert calc.ampacity_a("8 AWG", 90) == 55


def test_ampacity_of_an_unknown_size_is_an_error() -> None:
    with pytest.raises(KeyError, match="7 AWG"):
        calc.ampacity_a("7 AWG", 75)


@pytest.mark.parametrize(
    ("ambient_c", "factor"),
    [(10, 1.15), (30, 1.00), (31, 0.96), (35, 0.96), (36, 0.91), (60, 0.71)],
)
def test_temperature_correction_90_c_column(ambient_c: float, factor: float) -> None:
    assert calc.temperature_correction(ambient_c) == factor


def test_temperature_correction_above_85_c_leaves_no_ampacity() -> None:
    assert calc.temperature_correction(90) == 0.0


@pytest.mark.parametrize(
    ("clearance_mm", "adder_c"),
    [(0, 33), (13, 33), (25, 22), (90, 22), (200, 17), (500, 14), (901, 0)],
)
def test_rooftop_temperature_adder(clearance_mm: float, adder_c: float) -> None:
    assert calc.rooftop_adder_c(clearance_mm) == adder_c


@pytest.mark.parametrize(
    ("conductors", "factor"),
    [(2, 1.0), (3, 1.0), (4, 0.8), (6, 0.8), (7, 0.7), (12, 0.5), (50, 0.35)],
)
def test_bundling_factor(conductors: int, factor: float) -> None:
    assert calc.bundling_factor(conductors) == factor


def test_dc_string_circuit_matches_the_worked_example(spec: PvSystemSpec) -> None:
    values = calc.derive(spec)
    c_s1 = next(c for c in values.circuits if c.circuit_id == "C-S1")
    assert c_s1.i_max_a == pytest.approx(17.5)
    assert c_s1.ampacity_75_a == 35
    assert c_s1.t_effective_c == 60
    assert c_s1.k_temp == 0.71
    assert c_s1.k_fill == 0.8
    assert c_s1.ampacity_corrected_a == pytest.approx(22.72, abs=0.005)
    assert c_s1.vd_pct == pytest.approx(0.92, abs=0.005)


def test_circuit_sharing_a_raceway_inherits_its_bundle(spec: PvSystemSpec) -> None:
    values = calc.derive(spec)
    c_s2 = next(c for c in values.circuits if c.circuit_id == "C-S2")
    assert c_s2.k_fill == 0.8
    assert c_s2.t_effective_c == 60


def test_ac_inverter_output_circuit_matches_the_worked_example(spec: PvSystemSpec) -> None:
    values = calc.derive(spec)
    c_inv = next(c for c in values.circuits if c.circuit_id == "C-INV")
    assert c_inv.i_max_a == pytest.approx(27.3)
    assert c_inv.ocpd_id == "ITM-1"
    assert c_inv.ocpd_rating_a == 35
    assert c_inv.ocpd_min_a == 35  # 1.25 x 27.3 = 34.1 A -> next standard rating
    assert c_inv.vd_pct == pytest.approx(1.91, abs=0.005)
    assert c_inv.ampacity_corrected_a == pytest.approx(52.8, abs=0.05)  # 55 A x 0.96


def test_voltage_drop_formulas() -> None:
    tables = get_tables("NOM-001-SEDE-2012")
    # DC 2-wire: 2 x 25 m x 4.07 ohm/km x 13.22 A = 2.69 V of 291.2 V
    dc = calc.voltage_drop_dc_pct("10 AWG", 25, 13.22, 291.2, tables)
    assert dc == pytest.approx(0.924, abs=0.001)
    # AC single-phase 2-wire: 2 x 30 m x 2.56 ohm/km x 27.3 A = 4.19 V of 220 V
    ac = calc.voltage_drop_ac_pct("8 AWG", 30, 27.3, 220, 2, tables)
    assert ac == pytest.approx(1.906, abs=0.001)
    # three-phase uses sqrt(3) instead of 2
    three = calc.voltage_drop_ac_pct("8 AWG", 30, 27.3, 220, 3, tables)
    assert three == pytest.approx(1.906 * 3**0.5 / 2, abs=0.001)


# --- Whole-system values ---------------------------------------------------------------------


def test_system_totals_match_the_sample(spec: PvSystemSpec) -> None:
    values = calc.derive(spec)
    assert values.kwp_total == pytest.approx(7.70)
    assert values.kwac_total == pytest.approx(6.0)
    assert values.dc_ac_ratio == pytest.approx(1.2833, abs=0.0001)
    assert values.t_cell_max_c == 73


def test_per_string_values(spec: PvSystemSpec) -> None:
    values = calc.derive(spec)
    s1 = values.strings[0]
    assert (s1.string_id, s1.mppt_id, s1.n_parallel) == ("S1", "A", 1)
    assert s1.voc_max_string_v == pytest.approx(373.4, abs=0.05)
    assert s1.vmp_stc_string_v == pytest.approx(291.2, abs=0.05)
    assert s1.p_stc_w == pytest.approx(3850)
    assert s1.isc_input_a == pytest.approx(17.5)


def test_two_strings_on_one_mppt_count_as_parallel() -> None:
    spec = parse_spec(mutated(lambda s: s["strings"][1].update({"mppt": "A"})))
    values = calc.derive(spec)
    assert [v.n_parallel for v in values.strings] == [2, 2]
    assert values.strings[0].isc_input_a == pytest.approx(35.0)


def test_unknown_edition_is_an_error() -> None:
    with pytest.raises(KeyError, match="NOM-999"):
        get_tables("NOM-999")
    assert get_tables("NOM-001-SEDE-2012") is NOM_001_SEDE_2012


def test_tables_are_consistent() -> None:
    tables = NOM_001_SEDE_2012
    sizes = set(tables.ampacity_cu)
    assert sizes == set(tables.resistance_dc_ohm_km) == set(tables.resistance_ac_pvc_ohm_km)
    assert sizes == set(tables.awg_mm2)
    for cols in tables.ampacity_cu.values():
        assert cols[0] <= cols[1] <= cols[2]
    assert list(tables.standard_ocpd_a) == sorted(tables.standard_ocpd_a)
