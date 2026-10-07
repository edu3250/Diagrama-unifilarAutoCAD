"""NOCT values, per-model inverter voltages, AC reference voltage and configurable DC breakers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from catalogue_helpers import ET_MODULE, GROWATT, INVERTER, RECORDS, SUNTREE, raw, write
from pvsld.catalogue import (
    CatalogueError,
    ComponentRegistry,
    DcBreaker,
    Inverter,
    PVModule,
    read_record,
)


@pytest.fixture(scope="module")
def registry() -> ComponentRegistry:
    return ComponentRegistry.load(RECORDS, include_unreviewed=True)


def _fails(tmp_path: Path, relative: str, data: dict[str, Any], expected: str) -> None:
    path = write(tmp_path, relative, data)
    with pytest.raises(CatalogueError, match=expected):
        read_record(path)


# --- ET Solar module: NOCT ----------------------------------------------------------------------


def test_monofacial_module_keeps_noct_values(registry: ComponentRegistry) -> None:
    module = registry.get("ETSOLAR-ET-M672BH550")
    assert isinstance(module, PVModule)
    assert module.bifacial is False
    assert module.bnpi is None
    assert module.noct_c == 45
    assert module.noct is not None
    assert (module.noct.pmax_w, module.noct.vmp_v, module.noct.isc_a) == (410, 38.25, 11.35)
    assert module.power_tolerance_w == (0, 5)
    assert module.power_tolerance_pct is None


def test_noct_point_is_checked_like_the_stc_point(tmp_path: Path) -> None:
    data = raw(ET_MODULE)
    data["variants"][0]["noct"]["vmp_v"] = 60.0
    _fails(tmp_path, ET_MODULE, data, r"variant ETSOLAR-ET-M672BH520 noct: vmp_v \(60\) must be")


def test_noct_power_must_be_below_stc_power(tmp_path: Path) -> None:
    data = raw(ET_MODULE)
    data["variants"][0]["noct"] = {**data["variants"][0]["noct"], "pmax_w": 520.0}
    data["variants"][0]["noct"]["vmp_v"] = 40.44
    data["variants"][0]["noct"]["imp_a"] = 12.86
    _fails(tmp_path, ET_MODULE, data, r"noct: pmax_w \(520\) must be lower than the STC")


def test_noct_values_need_the_family_noct_temperature(tmp_path: Path) -> None:
    data = raw(ET_MODULE)
    del data["noct_c"]
    _fails(tmp_path, ET_MODULE, data, "noct values need the family value noct_c")


def test_bnpi_is_rejected_on_a_monofacial_module(tmp_path: Path) -> None:
    data = raw(ET_MODULE)
    data["variants"][0]["bnpi"] = dict(data["variants"][0]["noct"])
    _fails(tmp_path, ET_MODULE, data, "bnpi is only valid for a bifacial module")


# --- Growatt inverter: per-model voltage limits and AC reference voltage ---------------------


def test_inverter_voltage_limits_resolve_per_variant(registry: ComponentRegistry) -> None:
    low = registry.get("GROWATT-MIN-3000TL-X2")
    high = registry.get("GROWATT-MIN-3600TL-X2")
    huawei = registry.get("HUAWEI-SUN2000-5KTL-L1")
    assert isinstance(low, Inverter)
    assert isinstance(high, Inverter)
    assert isinstance(huawei, Inverter)
    assert (low.max_input_voltage_v, low.mppt_voltage_range_v) == (500, (40, 500))
    assert (high.max_input_voltage_v, high.mppt_voltage_range_v) == (550, (40, 550))
    assert (huawei.max_input_voltage_v, huawei.mppt_voltage_range_v) == (600, (90, 560))


def test_voltage_limit_defined_at_both_levels_is_rejected(tmp_path: Path) -> None:
    data = raw(GROWATT)
    data["max_input_voltage_v"] = 550
    _fails(tmp_path, GROWATT, data, "max_input_voltage_v is defined on the family and on the")


def test_voltage_limit_defined_at_no_level_is_rejected(tmp_path: Path) -> None:
    data = raw(GROWATT)
    del data["variants"][2]["mppt_voltage_range_v"]
    _fails(
        tmp_path,
        GROWATT,
        data,
        "variant GROWATT-MIN-3600TL-X2: mppt_voltage_range_v is not defined; set it on the family",
    )


def test_variant_window_is_checked_against_its_own_max_voltage(tmp_path: Path) -> None:
    data = raw(GROWATT)
    data["variants"][0]["mppt_voltage_range_v"] = [40, 550]  # 2500TL allows 500 V only
    _fails(tmp_path, GROWATT, data, r"variant GROWATT-MIN-2500TL-X2: mppt_voltage_range_v upper")


def test_family_level_voltage_applies_to_every_variant(tmp_path: Path) -> None:
    data = raw(INVERTER)
    data["variants"][0]["max_input_voltage_v"] = 600
    _fails(tmp_path, INVERTER, data, "defined on the family and on the variant")


def test_ac_current_is_checked_at_the_reference_voltage(registry: ComponentRegistry) -> None:
    growatt = registry.get("GROWATT-MIN-5000TL-X2")
    assert isinstance(growatt, Inverter)
    assert growatt.rated_ac_voltage_v == [230]
    assert growatt.max_ac_current_reference_voltage_v == 220
    huawei = registry.get("HUAWEI-SUN2000-5KTL-L1")
    assert isinstance(huawei, Inverter)
    assert huawei.max_ac_current_reference_voltage_v is None


def test_without_the_reference_voltage_the_growatt_currents_do_not_fit_230_v(
    tmp_path: Path,
) -> None:
    data = raw(GROWATT)
    del data["max_ac_current_reference_voltage_v"]
    _fails(tmp_path, GROWATT, data, r"variant GROWATT-MIN-\d+TL-X2: max_ac_output_current_a")


def test_a_wrong_reference_voltage_is_reported_with_its_value(tmp_path: Path) -> None:
    data = raw(GROWATT)
    data["max_ac_current_reference_voltage_v"] = 120
    _fails(tmp_path, GROWATT, data, r"at max_ac_current_reference_voltage_v \(120\) within 3%")


def test_inverters_have_no_certification_fields(tmp_path: Path) -> None:
    data = raw(INVERTER)
    data["certifications_grid"] = ["G99"]
    _fails(tmp_path, INVERTER, data, "certifications_grid: Extra inputs are not permitted")


# --- Suntree DC breaker: configurable poles and voltage -----------------------------------------


def test_one_breaker_per_rated_current(registry: ComponentRegistry) -> None:
    ratings = {b.component_id: b.rated_current_a for b in registry.dc_breakers()}
    suntree = {k: v for k, v in ratings.items() if k.startswith("SUNTREE")}
    assert suntree == {
        f"SUNTREE-SL7N-63-{amps}A": float(amps) for amps in (6, 10, 16, 20, 25, 32, 40, 50, 63)
    }
    breaker = registry.get("SUNTREE-SL7N-63-32A")
    assert isinstance(breaker, DcBreaker)
    assert breaker.poles is None
    assert breaker.ue_options_v(2) == [125, 375, 550, 600, 800]
    assert breaker.ue_options_v(5) == []


@pytest.mark.parametrize(
    ("poles", "voltage_v", "expected"),
    [
        (2, 800, 6.0),  # listed configuration
        (2, 550, 6.0),  # a 2P 800 V version covers a 550 V circuit
        (4, 1200, 6.0),
        (4, 1000, 6.0),
        (1, 100, 2.0),  # fallback: "other configurations"
        (3, 700, 2.0),
        (3, 900, None),  # no 3P version above 800 V
        (2, 801, None),
        (5, 100, None),  # no 5P version
    ],
)
def test_breaking_capacity_matches_the_listed_entry_or_falls_back(
    registry: ComponentRegistry, poles: int, voltage_v: float, expected: float | None
) -> None:
    breaker = registry.get("SUNTREE-SL7N-63-16A")
    assert isinstance(breaker, DcBreaker)
    assert breaker.breaking_capacity_ka(poles, voltage_v) == expected


def test_without_a_fallback_entry_an_unlisted_configuration_has_no_capacity(
    tmp_path: Path,
) -> None:
    data = raw(SUNTREE)
    del data["breaking_capacity_dc"][2]
    path = write(tmp_path, SUNTREE, data)
    breaker = ComponentRegistry.load(tmp_path, include_unreviewed=True).get("SUNTREE-SL7N-63-6A")
    assert isinstance(breaker, DcBreaker)
    assert read_record(path)
    assert breaker.breaking_capacity_ka(1, 100) is None
    assert breaker.breaking_capacity_ka(2, 800) == 6.0


def test_duplicate_rated_current_in_a_family_is_rejected(tmp_path: Path) -> None:
    data = raw(SUNTREE)
    data["variants"][1]["rated_current_a"] = 6
    _fails(tmp_path, SUNTREE, data, r"duplicate rated_current_a 6 A in the family")


def test_rated_current_above_the_frame_is_rejected(tmp_path: Path) -> None:
    data = raw(SUNTREE)
    data["variants"][-1]["rated_current_a"] = 80
    _fails(tmp_path, SUNTREE, data, r"rated_current_a \(80\) exceeds frame_current_a \(63\)")


def test_fixed_poles_and_pole_options_are_mutually_exclusive(tmp_path: Path) -> None:
    data = raw(SUNTREE)
    data["poles"] = 2
    _fails(tmp_path, SUNTREE, data, "mutually exclusive")


def test_a_range_needs_poles_or_pole_options(tmp_path: Path) -> None:
    data = raw(SUNTREE)
    del data["pole_options"]
    _fails(tmp_path, SUNTREE, data, "give either poles and rated_voltage_v, or pole_options")


def test_entry_for_a_pole_count_the_range_does_not_offer_is_rejected(tmp_path: Path) -> None:
    data = raw(SUNTREE)
    data["breaking_capacity_dc"][0]["poles"] = 5
    _fails(tmp_path, SUNTREE, data, "5 poles is not offered by this range")


def test_entry_above_the_highest_offered_voltage_is_rejected(tmp_path: Path) -> None:
    data = raw(SUNTREE)
    data["breaking_capacity_dc"][0]["voltage_v"] = 900  # 2P offers up to 800 V
    _fails(tmp_path, SUNTREE, data, "900 V is above every rated voltage offered for 2 poles")


def test_duplicate_breaking_capacity_entry_is_rejected(tmp_path: Path) -> None:
    data = raw(SUNTREE)
    data["breaking_capacity_dc"].append({"poles": None, "voltage_v": None, "icu_ka": 1.0})
    _fails(tmp_path, SUNTREE, data, r"duplicate entry \(None, None\)")


def test_unordered_ue_options_are_rejected(tmp_path: Path) -> None:
    data = raw(SUNTREE)
    data["pole_options"][1]["ue_v_options"] = [800, 125]
    _fails(tmp_path, SUNTREE, data, "ue_v_options of 2P must be ascending and unique")
