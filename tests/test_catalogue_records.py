"""The three committed records (Jinko, Huawei, Schneider) validate and expand into components."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from catalogue_helpers import ALL_RECORDS, BREAKER, INVERTER, MODULE, RECORDS, raw
from pvsld.catalogue import (
    ComponentRegistry,
    DcBreaker,
    Inverter,
    InverterFamily,
    ProtectionFamily,
    PVModule,
    PVModuleFamily,
    read_record,
)


@pytest.fixture(scope="module")
def registry() -> ComponentRegistry:
    return ComponentRegistry.load(RECORDS, include_unreviewed=True)


def test_records_expand_to_ten_modules_fourteen_inverters_ten_breakers(
    registry: ComponentRegistry,
) -> None:
    assert (len(registry.modules()), len(registry.inverters()), len(registry.dc_breakers())) == (
        10,
        14,
        10,
    )
    assert len(registry) == 34


def test_expanded_module_merges_family_and_variant_values(registry: ComponentRegistry) -> None:
    module = registry.get("JINKO-JKM640N-66HL4M-BDV")
    assert isinstance(module, PVModule)
    assert module.pmax_w == 640
    assert module.cells == 132  # family value
    assert module.family_id == "JINKO-JKM-66HL4M-BDV"
    assert module.temp_coef_voc_pct_per_c == -0.25
    assert module.bnpi is not None
    assert module.bnpi.isc_a == 18.03
    assert module.area_m2 == pytest.approx(2.382 * 1.134)
    assert module.source.extraction_method == "rendered_page"
    assert module.power_tolerance_pct == (0, 3)


def test_every_power_level_is_its_own_module(registry: ComponentRegistry) -> None:
    powers = {
        m.component_id: m.pmax_w for m in registry.modules() if m.family_id.startswith("JINKO")
    }
    assert powers == {f"JINKO-JKM{power}N-66HL4M-BDV": float(power) for power in range(625, 655, 5)}


def test_expanded_inverter_keeps_per_model_values(registry: ComponentRegistry) -> None:
    inverter = registry.get("HUAWEI-SUN2000-5KTL-L1")
    assert isinstance(inverter, Inverter)
    assert inverter.component_type == "hybrid_inverter"
    assert inverter.rated_ac_power_w == 5000
    assert inverter.max_ac_output_current_a == 25.0
    assert inverter.max_input_current_per_mppt_a == 12.5  # family value
    assert inverter.max_short_circuit_current_per_mppt_a == 18
    assert inverter.battery is not None
    assert inverter.battery.max_charge_power_w == 5000


def test_str_007_limit_uses_optimizer_power_only_on_the_model_that_has_it(
    registry: ComponentRegistry,
) -> None:
    six = registry.get("HUAWEI-SUN2000-6KTL-L1")
    assert isinstance(six, Inverter)
    assert six.max_pv_power_with_optimizers_wp == 10000
    assert six.max_pv_power_with_optimizers_ambiguous is True
    assert six.pv_power_limit_w(optimizers_on_all_modules=False) == 9000
    assert six.pv_power_limit_w(optimizers_on_all_modules=True) == 10000

    five = registry.get("HUAWEI-SUN2000-5KTL-L1")
    assert isinstance(five, Inverter)
    assert five.max_pv_power_with_optimizers_wp is None
    assert five.pv_power_limit_w(optimizers_on_all_modules=False) == 7500
    assert five.pv_power_limit_w(optimizers_on_all_modules=True) == 7500


def test_phase_two_owner_case_exceeds_the_six_kw_inverter_limit(
    registry: ComponentRegistry,
) -> None:
    """2 x 11 x 550 W = 12.1 kWp is above every limit of the catalogue's 6KTL (9 / 10 kWp)."""
    six = registry.get("HUAWEI-SUN2000-6KTL-L1")
    assert isinstance(six, Inverter)
    assert six.pv_power_limit_w(optimizers_on_all_modules=True) < 12_100


def test_breaker_breaking_capacity_depends_on_voltage(registry: ComponentRegistry) -> None:
    breaker = registry.get("SCHNEIDER-A9N61652")
    assert isinstance(breaker, DcBreaker)
    assert breaker.rated_current_a == 20
    assert breaker.rated_voltage_v == 800
    assert breaker.breaking_capacity_ka(2, 600) == 3.0
    assert breaker.breaking_capacity_ka(2, 650) == 3.0
    assert breaker.breaking_capacity_ka(2, 651) == 1.5  # next tabulated voltage is the safe one
    assert breaker.breaking_capacity_ka(2, 800) == 1.5
    assert breaker.breaking_capacity_ka(2, 801) is None  # above the rated voltage
    assert breaker.breaking_capacity_ka(4, 600) is None  # the range is 2P only


def test_records_keep_their_provenance_and_notes() -> None:
    jinko = read_record(RECORDS / MODULE)
    assert jinko.source.filename == "JKM625-650N-66HL4M-BDV-Z1-EU.pdf"
    assert jinko.source.extraction_method == "rendered_page"
    assert "rendered with pypdfium2" in (jinko.source.notes or "")
    huawei = read_record(RECORDS / INVERTER)
    assert "column order" in (huawei.source.notes or "")
    assert "Footnote 1" in (huawei.source.notes or "")
    for relative in ALL_RECORDS:
        source = read_record(RECORDS / relative).source
        assert len(source.sha256) == 64
        assert source.pages


def test_record_files_are_named_after_their_family() -> None:
    for relative in ALL_RECORDS:
        family = read_record(RECORDS / relative)
        assert (RECORDS / relative).stem == family.family_id.lower()


@pytest.mark.parametrize(
    ("relative", "model"),
    [(MODULE, PVModuleFamily), (INVERTER, InverterFamily), (BREAKER, ProtectionFamily)],
)
def test_yaml_to_model_to_dict_round_trip_is_lossless(relative: str, model: Any) -> None:
    original = raw(relative)
    family = model.model_validate(original)

    dumped = family.model_dump(mode="json", exclude_unset=True)
    assert dumped == json.loads(json.dumps(original, default=str))  # dates become ISO strings

    again = model.model_validate(yaml.safe_load(yaml.safe_dump(dumped)))
    assert again == family
