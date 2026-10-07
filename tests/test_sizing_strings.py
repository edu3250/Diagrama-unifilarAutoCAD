"""Stage 3.4: string configurations are enumerated and checked against module, inverter, site."""

from __future__ import annotations

from typing import Any

import pytest

from pvsld.core.model import Site
from pvsld.core.policy import DcAcPolicy
from pvsld.core.severity import Severity
from pvsld.sizing import adapters
from pvsld.sizing.strings import (
    EvalContext,
    Evaluation,
    enumerate_configs,
    evaluate_config,
    strings_per_mppt,
)
from sizing_helpers import (
    ET_550,
    GROWATT_5K,
    HUAWEI_5K,
    HUAWEI_6K,
    JINKO_650,
    SAMPLE_INVERTER,
    SAMPLE_MODULE,
    registry,
    template,
)


def _context(
    module_id: str = SAMPLE_MODULE, inverter_id: str = SAMPLE_INVERTER, **changes: Any
) -> EvalContext:
    module = registry().get(module_id)
    values: dict[str, Any] = {
        "module": module,
        "spec_module": adapters.to_spec_module(module),  # type: ignore[arg-type]
        "inverter": registry().get(inverter_id),
        "site": Site.model_validate(template()["project"]["site"]),
        "voc_method": "coefficient",
        "cell_temp_rise_c": 35.0,
        "optimizers_on_all_modules": False,
        "policy": DcAcPolicy(),
    }
    values.update(changes)
    return EvalContext(**values)


def _rules(evaluation: Evaluation, severity: Severity = Severity.ERROR) -> list[str]:
    return [i.rule_id for i in evaluation.issues if i.severity is severity]


# --- Temperature-corrected voltages (vault: PV String Sizing, worked example) -----------------


def test_voltage_window_of_the_vault_worked_example() -> None:
    ctx = _context()
    assert ctx.voc_cold_module_v == pytest.approx(53.35, abs=0.01)
    assert ctx.n_max == 11  # floor(600 / 53.35)
    assert ctx.vmp_hot_module_v == pytest.approx(34.61, abs=0.01)
    assert ctx.n_min_operating == 3  # ceil(90 / 34.61)


def test_string_values_are_temperature_corrected() -> None:
    evaluation = evaluate_config(_context(), 2, 7)
    m = evaluation.metrics
    assert m.voc_cold_string_v == pytest.approx(373.4, abs=0.1)
    assert m.vmp_hot_string_v == pytest.approx(242.3, abs=0.1)
    assert m.vmp_cold_string_v == pytest.approx(7 * 45.68, abs=0.1)
    assert m.p_dc_w == 7700
    assert m.dc_ac_ratio == pytest.approx(1.2833, abs=1e-4)
    assert evaluation.feasible
    assert evaluation.issues == ()


# --- Rejections -------------------------------------------------------------------------------


def test_overvoltage_is_rejected_with_volt_001_and_the_dwelling_limit() -> None:
    evaluation = evaluate_config(_context(), 2, 12)
    assert not evaluation.feasible
    assert _rules(evaluation)[0] == "VOLT-001"
    assert "VOLT-003" in _rules(evaluation)  # dwelling: 640.2 V > 600 V
    first = evaluation.errors[0].message_es
    assert "640.2 V" in first
    assert "600 V" in first
    assert "máximo 11 módulos" in first


def test_dwelling_limit_does_not_apply_to_commercial_occupancy() -> None:
    site = Site.model_validate(template()["project"]["site"]).model_copy(
        update={"occupancy": "comercial"}
    )
    inverter = registry().get(SAMPLE_INVERTER).model_copy(update={"max_input_voltage_v": 1000.0})
    ctx = _context(site=site, inverter=inverter)
    assert _rules(evaluate_config(ctx, 1, 12)) == []
    assert ctx.n_max == 18  # floor(1000 / 53.35)


def test_module_system_voltage_limit_is_volt_002() -> None:
    module = registry().get(SAMPLE_MODULE).model_copy(update={"max_system_voltage_v": 450.0})
    rules = _rules(evaluate_config(_context(module=module), 1, 9))  # 480.2 V
    assert "VOLT-002" in rules


def test_overpower_is_rejected_with_str_007() -> None:
    evaluation = evaluate_config(_context(), 2, 11)
    assert _rules(evaluation) == ["STR-007"]
    message = evaluation.errors[0].message_es
    assert "12.10 kWp" in message
    assert "9.00 kWp" in message


def test_power_exactly_at_the_limit_is_accepted() -> None:
    inverter = (
        registry().get(SAMPLE_INVERTER).model_copy(update={"recommended_max_pv_power_wp": 7700.0})
    )
    assert evaluate_config(_context(inverter=inverter), 2, 7).feasible


def test_dc_ac_ratio_follows_the_policy() -> None:
    warned = evaluate_config(_context(), 2, 8)  # 8.8 kWp / 6 kW = 1.47
    assert warned.feasible
    assert _rules(warned, Severity.WARNING) == ["STR-007"]
    strict = _context(policy=DcAcPolicy(warn_above=1.3, error_above=1.4))
    assert _rules(evaluate_config(strict, 2, 8)) == ["STR-007"]
    lax = _context(policy=DcAcPolicy(warn_above=1.6, error_above=1.8))
    assert evaluate_config(lax, 2, 8).issues == ()


def test_optimizer_only_power_limit_applies_only_when_declared() -> None:
    assert registry().get(HUAWEI_6K).pv_power_limit_w(False) == 9000  # type: ignore[union-attr]
    lax = DcAcPolicy(warn_above=1.6, error_above=1.8)
    plain = _context(inverter_id=HUAWEI_6K, policy=lax)
    optimized = _context(inverter_id=HUAWEI_6K, policy=lax, optimizers_on_all_modules=True)
    assert _rules(evaluate_config(plain, 2, 9)) == ["STR-007"]  # 9.9 kWp > 9 kW
    assert evaluate_config(optimized, 2, 9).feasible  # 9.9 kWp <= 10 kW with optimizers


def test_short_strings_fall_below_the_mppt_window() -> None:
    evaluation = evaluate_config(_context(), 1, 2)
    assert _rules(evaluation) == ["STR-001"]
    assert "mínimo 3 módulos" in evaluation.errors[0].message_es


def test_cold_vmp_above_the_mppt_maximum_is_str_002() -> None:
    inverter = (
        registry().get(SAMPLE_INVERTER).model_copy(update={"mppt_voltage_range_v": (90.0, 300.0)})
    )
    assert "STR-002" in _rules(evaluate_config(_context(inverter=inverter), 1, 8))  # 365 V


def test_hot_vmp_below_the_startup_voltage_only_warns() -> None:
    evaluation = evaluate_config(_context(), 1, 3)  # 103.8 V: above 90 V, below 120 V start-up
    assert evaluation.feasible
    assert _rules(evaluation, Severity.WARNING)[0] == "STR-003"


def test_requested_module_count_range_rejects_outside_configurations() -> None:
    ctx = _context(module_count_min=12, module_count_max=14)
    assert evaluate_config(ctx, 2, 7).feasible
    assert _rules(evaluate_config(ctx, 2, 5)) == ["REQ-001"]  # 10 modules
    assert _rules(evaluate_config(ctx, 2, 8)) == ["REQ-001"]  # 16 modules


# --- Current limits: bifacial BNPI and clipping -----------------------------------------------


def test_bifacial_bnpi_isc_above_the_mppt_limit_is_rejected_str_004() -> None:
    evaluation = evaluate_config(_context(JINKO_650, HUAWEI_5K), 1, 8)
    assert "STR-004" in _rules(evaluation)
    message = next(i.message_es for i in evaluation.errors if i.rule_id == "STR-004")
    assert "18.16 A BNPI" in message
    assert "22.70 A" in message
    assert evaluation.metrics.isc_design_a == 18.16


def test_bifacial_bnpi_isc_within_the_growatt_limit_passes() -> None:
    evaluation = evaluate_config(_context(JINKO_650, GROWATT_5K), 2, 5)
    assert evaluation.feasible
    assert evaluation.metrics.isc_input_a == pytest.approx(22.7)  # 1.25 x 18.16 <= 24 A
    assert evaluation.metrics.clipping_pct == 0  # Imp 15.64 A <= 16 A


def test_imp_above_the_mppt_current_warns_with_the_estimated_clipping() -> None:
    evaluation = evaluate_config(_context(ET_550, HUAWEI_5K), 2, 6)
    assert evaluation.feasible
    assert _rules(evaluation, Severity.WARNING) == ["STR-005"]
    assert evaluation.metrics.clipping_pct == pytest.approx(100 * (1 - 12.5 / 13.48), abs=0.01)
    message = evaluation.warnings[0].message_es
    assert "13.48 A" in message
    assert "12.5 A" in message
    assert evaluation.metrics.deliverable_dc_w == pytest.approx(
        6600 * (1 - evaluation.metrics.clipping_pct / 100)
    )


def test_bifacial_clipping_message_reports_the_bnpi_current() -> None:
    evaluation = evaluate_config(_context(JINKO_650, HUAWEI_5K), 2, 5)
    clipping = next(i for i in evaluation.issues if i.rule_id == "STR-005")
    assert "15.64 A" in clipping.message_es
    assert "17.24 A" in clipping.message_es  # BNPI Imp


def test_strings_are_spread_over_the_mppts_round_robin() -> None:
    inverter = registry().get(SAMPLE_INVERTER).model_copy(update={"inputs_per_mppt": 2})
    assert strings_per_mppt(inverter, 1) == [1, 0]  # type: ignore[arg-type]
    assert strings_per_mppt(inverter, 2) == [1, 1]  # type: ignore[arg-type]
    assert strings_per_mppt(inverter, 3) == [2, 1]  # type: ignore[arg-type]
    assert strings_per_mppt(inverter, 4) == [2, 2]  # type: ignore[arg-type]


def test_two_strings_on_one_mppt_double_the_input_current() -> None:
    inverter = registry().get(SAMPLE_INVERTER).model_copy(update={"inputs_per_mppt": 2})
    evaluation = evaluate_config(_context(inverter=inverter), 4, 4)
    assert evaluation.metrics.strings_per_mppt == 2
    assert evaluation.metrics.isc_input_a == pytest.approx(2 * 1.25 * 14.0)  # 35 A > 22 A
    assert "STR-004" in _rules(evaluation)


# --- Enumeration ------------------------------------------------------------------------------


def test_enumeration_covers_one_step_beyond_each_voltage_bound() -> None:
    configs = list(enumerate_configs(_context()))
    series = {n for _, n in configs}
    assert min(series) == 2  # one below the operating minimum (3)
    assert max(series) == 12  # one above the voltage maximum (11)
    assert {s for s, _ in configs} == {1, 2}  # two MPPTs with one input each
    assert len(configs) == 2 * 11
