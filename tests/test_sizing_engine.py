"""Stage 3.4: the sizing engine end to end (plan example, owner scenarios, invariants)."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from pvsld.core.policy import DcAcPolicy
from pvsld.core.severity import Severity
from pvsld.core.validation import validate_pv_design
from pvsld.sizing import (
    SizingInputError,
    SizingResult,
    format_report,
    request_from_mapping,
    size_pv_system,
)
from s1_helpers import load_example
from sizing_helpers import (
    ET_550,
    GROWATT_5K,
    HUAWEI_5K,
    HUAWEI_6K,
    JINKO_650,
    SAMPLE_INVERTER,
    SAMPLE_MODULE,
    SCHNEIDER_20A,
    make_request,
    registry,
    size,
    template,
    validate_selected,
)


def _rejection(result: SizingResult, label: str, inverter: str | None = None):  # type: ignore[no-untyped-def]
    found = [
        r
        for r in result.rejected
        if r.config.label == label and (inverter is None or r.config.inverter_id == inverter)
    ]
    assert len(found) == 1, f"expected one rejection of {label}, got {len(found)}"
    return found[0]


def _issue_ids(item: Any) -> list[str]:
    return [i.rule_id for i in item.issues]


# --- The Phase 2 owner test (plan, Stage 3.4) -------------------------------------------------


@pytest.fixture(scope="module")
def phase_2_owner_test() -> SizingResult:
    """550 W module, 6 kW inverter (Pdc max 9 kW, Vdc max 600 V), T_min -3 C, aiming at 2 x 12."""
    return size(SAMPLE_MODULE, [SAMPLE_INVERTER], target_dc_power_w=13200)


def test_2_by_12_is_rejected_by_volt_001(phase_2_owner_test: SizingResult) -> None:
    rejection = _rejection(phase_2_owner_test, "2×12")
    assert rejection.rule_id == "VOLT-001"
    assert "640.2 V" in rejection.errors[0].message_es


def test_2_by_11_is_rejected_by_str_007(phase_2_owner_test: SizingResult) -> None:
    rejection = _rejection(phase_2_owner_test, "2×11")
    assert rejection.rule_ids == ("STR-007",)
    assert "12.10 kWp" in rejection.errors[0].message_es
    assert "9.00 kWp" in rejection.errors[0].message_es


def test_2_by_8_is_selected_with_its_reported_figures(phase_2_owner_test: SizingResult) -> None:
    selected = phase_2_owner_test.selected
    assert selected is not None
    assert selected.config.label == "2×8"
    assert selected.metrics.p_dc_w == 8800
    assert selected.metrics.dc_ac_ratio == pytest.approx(1.467, abs=0.001)
    assert selected.metrics.voc_cold_string_v == pytest.approx(426.8, abs=0.1)
    assert [i.rule_id for i in selected.warnings] == ["STR-007"]  # DC/AC 1.47 > 1.35


def test_the_owner_test_selection_validates_with_zero_errors(
    phase_2_owner_test: SizingResult,
) -> None:
    report = validate_selected(phase_2_owner_test)
    assert report.ok
    assert report.errors == ()
    assert report.derived is not None
    assert report.derived.kwp_total == pytest.approx(8.8)


def test_every_alternative_is_rejected_with_a_reason(phase_2_owner_test: SizingResult) -> None:
    assert phase_2_owner_test.rejected
    for rejection in phase_2_owner_test.rejected:
        assert rejection.errors
        assert all(issue.message_es for issue in rejection.errors)
    assert {r.config.label for r in phase_2_owner_test.rejected if r.rule_id == "STR-007"} == {
        "2×9",
        "2×10",
        "2×11",
    }


def test_candidates_are_ranked_best_first(phase_2_owner_test: SizingResult) -> None:
    labels = [c.config.label for c in phase_2_owner_test.candidates]
    assert labels[:3] == ["2×8", "2×7", "2×6"]
    assert [c.rank for c in phase_2_owner_test.candidates] == list(range(1, len(labels) + 1))
    assert 1 <= len(labels) <= 10


# --- The residential example (plan: test_size_residential_7p7kwp) -----------------------------


def test_size_residential_7p7kwp_reproduces_the_sample() -> None:
    result = size(SAMPLE_MODULE, [SAMPLE_INVERTER], target_dc_power_w=7700)
    selected = result.selected
    assert selected is not None
    assert selected.config.label == "2×7"
    assert selected.issues == ()
    assert selected.findings == ()
    spec, sample = selected.spec, load_example()
    assert [(s["n_series"], s["mppt"]) for s in spec["strings"]] == [(7, "A"), (7, "B")]
    assert [c["conductors"]["size"] for c in spec["circuits"]] == [
        c["conductors"]["size"] for c in sample["circuits"]
    ]
    assert spec["ac_bos"]["ocpds"][0]["rating_a"] == sample["ac_bos"]["ocpds"][0]["rating_a"] == 35
    assert spec["inverters"][0]["iac_max_a"] == 27.3
    assert validate_selected(result).ok


def test_selected_conductors_agree_with_the_derived_values_of_the_rule_pack() -> None:
    result = size(SAMPLE_MODULE, [SAMPLE_INVERTER], target_dc_power_w=7700)
    report = validate_selected(result)
    assert report.derived is not None
    by_id = {c.circuit_id: c for c in report.derived.circuits}
    assert by_id["C-S1"].size == "10 AWG"
    assert by_id["C-S1"].vd_pct == pytest.approx(0.92, abs=0.01)  # vault: 25 m, 10 AWG
    assert by_id["C-S1"].ampacity_corrected_a is not None
    assert by_id["C-S1"].ampacity_corrected_a >= by_id["C-S1"].i_max_a  # type: ignore[operator]
    assert by_id["C-INV"].vd_pct == pytest.approx(1.91, abs=0.01)
    assert by_id["C-INV"].ocpd_rating_a == 35
    bos = {c.circuit_id: c for c in result.selected.bos.conductors}  # type: ignore[union-attr]
    assert bos["C-S"].size == by_id["C-S1"].size
    assert bos["C-INV"].size == by_id["C-INV"].size


# --- Owner scenarios with the real components (fixture copies of the datasheet records) -------


def test_jinko_650_on_huawei_5ktl_has_no_viable_configuration() -> None:
    result = size(JINKO_650, [HUAWEI_5K], target_dc_power_w=12000)
    assert not result.ok
    assert result.spec is None
    # Voc(T_min) = 53.80 V per module: 11 per string is the maximum (591.8 V <= 600 V)
    assert _rejection(result, "1×12").rule_id == "VOLT-001"
    assert "645.6 V" in _rejection(result, "1×12").errors[0].message_es
    assert "VOLT-001" not in {
        rule for r in result.rejected if r.config.n_series <= 11 for rule in r.rule_ids
    }
    # BNPI Isc 18.16 A (22.7 A with the 1.25 factor) exceeds the 18 A per MPPT: every config fails
    viable_by_voltage = [r for r in result.rejected if 3 <= r.config.n_series <= 11]
    assert viable_by_voltage
    assert all("STR-004" in r.rule_ids for r in viable_by_voltage)
    assert "18 A por MPPT" in _rejection(result, "2×8").errors[0].message_es


def test_jinko_650_on_huawei_5ktl_flags_clipping_and_the_power_limit() -> None:
    result = size(JINKO_650, [HUAWEI_5K], target_dc_power_w=12000)
    clipped = _rejection(result, "2×11")
    assert "STR-005" in _issue_ids(clipped)  # Imp 15.64 A > 12.5 A
    assert clipped.metrics is not None
    assert clipped.metrics.clipping_pct == pytest.approx(100 * (1 - 12.5 / 15.64), abs=0.01)
    assert "STR-007" in clipped.rule_ids  # 14.30 kWp > 7.5 kWp
    assert "14.30 kWp" in next(i for i in clipped.errors if i.rule_id == "STR-007").message_es


def test_jinko_650_on_growatt_min_5000_fits_without_clipping() -> None:
    result = size(JINKO_650, [GROWATT_5K], target_dc_power_w=9000)
    selected = result.selected
    assert selected is not None
    assert selected.config.label == "2×5"  # 6.5 kWp: 2 x 6 would be 7.8 kWp > 7.5 kWp
    assert selected.metrics.clipping_pct == 0  # Imp 15.64 A <= 16 A
    assert selected.metrics.isc_input_a == pytest.approx(22.7)  # BNPI 18.16 A, 1.25 x <= 24 A
    assert selected.issues == ()
    assert _rejection(result, "2×6").rule_id == "STR-007"
    assert _rejection(result, "1×11").rule_id == "VOLT-001"  # 591.8 V > 550 V
    assert validate_selected(result).ok
    module = result.spec["modules"][0]  # type: ignore[index]
    assert module["isc_a"] == 18.16  # BNPI current carried to the rule pack
    assert module["bifacial"] is True


def test_growatt_ac_breaker_uses_the_current_at_220_v() -> None:
    result = size(JINKO_650, [GROWATT_5K], target_dc_power_w=9000)
    spec = result.spec
    assert spec is not None
    assert spec["inverters"][0]["vac_v"] == 220
    assert spec["inverters"][0]["iac_max_a"] == 22.7  # specified at 220 V (owner, 2026-10-07)
    assert spec["ac_bos"]["ocpds"][0]["rating_a"] == 30  # 1.25 x 22.7 = 28.4 A


def test_et_solar_550_on_growatt_min_5000() -> None:
    result = size(ET_550, [GROWATT_5K], target_dc_power_w=9000)
    selected = result.selected
    assert selected is not None
    assert selected.config.label == "2×6"  # 6.6 kWp; 2 x 7 = 7.7 kWp > 7.5 kWp
    assert selected.issues == ()
    assert _rejection(result, "2×7").rule_id == "STR-007"
    assert validate_selected(result).ok


def test_et_solar_550_on_huawei_5ktl_selects_with_a_clipping_warning() -> None:
    result = size(ET_550, [HUAWEI_5K], target_dc_power_w=9000)
    selected = result.selected
    assert selected is not None
    assert [i.rule_id for i in selected.warnings] == ["STR-005"]
    assert selected.metrics.clipping_pct == pytest.approx(7.27, abs=0.01)
    assert validate_selected(result).ok


# --- DC breaker selection through the engine (Suntree vs Schneider) ---------------------------


def test_suntree_breaker_is_selected_when_a_string_breaker_is_requested() -> None:
    result = size(
        JINKO_650, [GROWATT_5K], target_dc_power_w=9000, dc_ocpd="always", dc_ocpd_device="breaker"
    )
    selected = result.selected
    assert selected is not None
    dc = selected.bos.dc_ocpd
    assert dc.required
    assert dc.device == "breaker"
    assert dc.device_id == "SUNTREE-SL7N-63-32A"
    assert dc.rating_a == 32
    breakers = [d for d in result.spec["dc_bos"]["disconnects"] if d["id"].startswith("DCB-")]  # type: ignore[index]
    assert [b["id"] for b in breakers] == ["DCB-S1", "DCB-S2"]
    assert all(b["ie_a"] == 32 and b["poles"] == 2 for b in breakers)
    assert all(b["ue_v"] >= selected.metrics.voc_cold_string_v for b in breakers)
    box = [d for d in result.spec["dc_bos"]["disconnects"] if d["id"] == "DCD-CD1"]  # type: ignore[index]
    assert box == [
        {
            "id": "DCD-CD1",
            "integrated_in": None,
            "poles": 4,
            "ue_v": breakers[0]["ue_v"],
            "ie_a": 32,
        }
    ]
    assert validate_selected(result).ok


def test_schneider_20_a_cannot_protect_the_jinko_650_so_every_configuration_fails() -> None:
    result = size(
        JINKO_650,
        [GROWATT_5K],
        target_dc_power_w=9000,
        dc_ocpd="always",
        dc_ocpd_device="breaker",
        dc_breakers=[SCHNEIDER_20A],
    )
    assert not result.ok
    bos_rejections = [r for r in result.rejected if r.stage == "bos"]
    assert bos_rejections
    assert all(r.rule_id == "OCP-002" for r in bos_rejections)
    message = bos_rejections[0].errors[-1].message_es
    assert "A9N61652" in message
    assert "20 A < 28.4 A" in message


def test_no_string_breaker_is_selected_for_one_string_per_input() -> None:
    selected = size(JINKO_650, [GROWATT_5K], target_dc_power_w=9000, dc_ocpd="auto").selected
    assert selected is not None
    assert not selected.bos.dc_ocpd.required
    assert "NOM 690-9(a)" in selected.bos.dc_ocpd.reason_es
    assert not any(d["id"].startswith("DCB-") for d in selected.spec["dc_bos"]["disconnects"])


# --- Choosing among catalogue inverters -------------------------------------------------------


def test_auto_inverters_screens_the_whole_catalogue() -> None:
    result = size(ET_550, "auto", target_dc_power_w=7000)
    assert result.ok
    assert len(result.inverters_evaluated) == len(registry().inverters())
    assert validate_selected(result).ok
    selected_inverters = {c.config.inverter_id for c in result.candidates}
    assert len(selected_inverters) >= 1
    # the objective compares the deliverable power (STC power minus current clipping) to the target
    assert result.selected.metrics.deliverable_dc_w == pytest.approx(7000, abs=500)  # type: ignore[union-attr]


def test_every_candidate_specification_passes_the_rule_pack_with_zero_errors() -> None:
    result = size(ET_550, "auto", target_dc_power_w=7000)
    assert len(result.candidates) == 10
    for candidate in result.candidates:
        report = validate_pv_design(candidate.spec)
        assert report.ok, [f.message_es for f in report.errors]


def test_a_service_voltage_no_inverter_supports_rejects_every_inverter() -> None:
    spec = template()
    spec["utility"]["system"] = "1F-2H"
    spec["utility"]["nominal_voltage_v"] = 127
    result = size(ET_550, [HUAWEI_5K, GROWATT_5K], template=spec)
    assert not result.ok
    assert [(r.stage, r.rule_id) for r in result.rejected] == [("inverter", "GEN-004")] * 2
    assert "127 V" in result.rejected[0].errors[0].message_es


def test_a_127_v_service_uses_one_phase_and_a_current_carrying_neutral() -> None:
    inverter = registry().get(GROWATT_5K).model_copy(update={"rated_ac_voltage_v": [127.0]})
    inverter = inverter.model_copy(update={"max_ac_current_reference_voltage_v": None})
    assert inverter.rated_ac_voltage_v == [127.0]
    spec = template()
    spec["utility"]["system"] = "1F-2H"
    spec["utility"]["nominal_voltage_v"] = 127
    spec["ac_bos"]["panels"][0]["system"] = "1F-2H"
    from pvsld.catalogue import ComponentRegistry

    custom = ComponentRegistry([*[c for c in registry() if c.component_id != GROWATT_5K], inverter])
    result = size_pv_system(
        make_request(ET_550, [GROWATT_5K], template=spec, target_dc_power_w=6000), custom
    )
    assert result.ok, format_report(result)
    assert result.spec is not None
    assert result.spec["inverters"][0]["phases"] == 1
    c_inv = next(c for c in result.spec["circuits"] if c["id"] == "C-INV")
    assert c_inv["conductors"]["qty"] == 1
    assert c_inv["raceway"]["ccc_count"] == 2
    assert result.spec["ac_bos"]["ocpds"][0]["poles"] == 1
    assert validate_selected(result).ok


# --- Request handling: ranges, policy, errors -------------------------------------------------


def test_module_count_range_limits_the_configurations() -> None:
    result = size(SAMPLE_MODULE, [SAMPLE_INVERTER], module_count_min=12, module_count_max=14)
    assert result.target_dc_power_w == 14 * 550  # no target: the largest allowed count
    assert result.selected is not None
    assert result.selected.config.n_modules == 14
    assert {c.config.n_modules for c in result.candidates} <= {12, 13, 14}
    assert "REQ-001" in {rule for r in result.rejected for rule in r.rule_ids}


def test_without_a_target_the_largest_deliverable_power_wins() -> None:
    result = size(SAMPLE_MODULE, [SAMPLE_INVERTER])
    assert result.target_dc_power_w is None
    assert result.selected is not None
    assert result.selected.config.label == "2×8"


def test_a_stricter_dc_ac_policy_changes_the_selection_consistently() -> None:
    policy = DcAcPolicy(warn_above=1.30, error_above=1.40)
    result = size(SAMPLE_MODULE, [SAMPLE_INVERTER], target_dc_power_w=13200, dc_ac_policy=policy)
    assert result.selected is not None
    assert result.selected.config.label == "2×7"  # 1.28; 2 x 8 (1.47) is now an error
    assert _rejection(result, "2×8").rule_id == "STR-007"
    assert validate_selected(result, policy).ok


def test_optimizer_declaration_raises_the_power_limit_to_the_datasheet_value() -> None:
    lax = DcAcPolicy(warn_above=1.6, error_above=1.8)
    plain = size(SAMPLE_MODULE, [HUAWEI_6K], target_dc_power_w=9900, dc_ac_policy=lax)
    assert plain.selected is not None
    assert plain.selected.config.n_modules < 18  # 9.9 kWp > 9 kW recommended maximum
    optimized = size(
        SAMPLE_MODULE,
        [HUAWEI_6K],
        target_dc_power_w=9900,
        dc_ac_policy=lax,
        optimizers_on_all_modules=True,
    )
    assert optimized.selected is not None
    assert optimized.selected.config.label == "2×9"
    assert optimized.spec["inverters"][0]["pdc_max_w"] == 10000  # type: ignore[index]
    assert "STR-009" in " ".join(optimized.assumptions)
    assert validate_selected(optimized, lax).ok


def test_results_are_deterministic() -> None:
    first = size(ET_550, "auto", target_dc_power_w=7000).to_dict()
    second = size(ET_550, "auto", target_dc_power_w=7000).to_dict()
    assert first == second


def test_result_serialises_to_plain_json_and_the_spec_round_trips() -> None:
    result = size(SAMPLE_MODULE, [SAMPLE_INVERTER], target_dc_power_w=13200)
    data = json.loads(json.dumps(result.to_dict()))
    assert data["ok"] is True
    assert data["selected"]["config"]["label"] == "2×8"
    assert validate_pv_design(data["selected"]["spec"]).ok  # dates came back as ISO strings
    assert "spec" not in data["alternatives"][0]
    assert {"inverter", "config", "rule_ids", "reasons"} <= set(data["rejected"][0])


def test_selected_spec_survives_a_yaml_round_trip() -> None:
    result = size(SAMPLE_MODULE, [SAMPLE_INVERTER], target_dc_power_w=7700)
    text = yaml.safe_dump(result.spec, allow_unicode=True)
    assert validate_pv_design(yaml.safe_load(text)).ok


def test_project_name_placeholder_is_replaced_with_the_designed_power() -> None:
    spec = template()
    spec["project"]["name"] = "Sistema fotovoltaico {kwp} kWp"
    result = size(SAMPLE_MODULE, [SAMPLE_INVERTER], target_dc_power_w=7700, template=spec)
    assert result.spec["project"]["name"] == "Sistema fotovoltaico 7.70 kWp"  # type: ignore[index]


def test_the_template_is_not_modified() -> None:
    spec = template()
    before = json.dumps(spec, default=str, sort_keys=True)
    size(SAMPLE_MODULE, [SAMPLE_INVERTER], template=spec)
    assert json.dumps(spec, default=str, sort_keys=True) == before


def test_report_names_the_selection_the_rejections_and_the_todo() -> None:
    text = format_report(size(SAMPLE_MODULE, [SAMPLE_INVERTER], target_dc_power_w=13200))
    assert "SELECTED: YI-6000 2×8" in text
    assert "VOLT-001" in text
    assert "STR-007" in text
    assert "TODO 3.4b" in text
    assert "rule pack mx-gd-2026.10: 0 errors" in text
    failed = format_report(size(JINKO_650, [HUAWEI_5K], target_dc_power_w=12000))
    assert "NO CANDIDATE" in failed
    assert "STR-004" in failed


def test_report_is_compact_enough_for_the_token_budget() -> None:
    text = format_report(size(ET_550, "auto", target_dc_power_w=7000))
    assert len(text) < 20_000  # the plan caps the result at 10k tokens (~40 kB of text)


# --- Errors -----------------------------------------------------------------------------------


def test_unknown_module_suggests_the_closest_id() -> None:
    with pytest.raises(SizingInputError, match="JINKO-JKM650N-66HL4M-BDV"):
        size("JINKO-JKM650N-66HL4M-BD", [GROWATT_5K])


def test_a_component_of_the_wrong_type_is_refused() -> None:
    with pytest.raises(SizingInputError, match="not a PVModule"):
        size(GROWATT_5K, [GROWATT_5K])
    with pytest.raises(SizingInputError, match="not a Inverter"):
        size(ET_550, [ET_550])


def test_a_module_voltage_class_outside_schema_0_1_0_is_refused() -> None:
    from pvsld.catalogue import ComponentRegistry

    odd = registry().get(ET_550).model_copy(update={"max_system_voltage_v": 1100.0})
    custom = ComponentRegistry([*[c for c in registry() if c.component_id != ET_550], odd])
    with pytest.raises(SizingInputError, match="1100 V"):
        size_pv_system(make_request(ET_550, [GROWATT_5K]), custom)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda s: s.pop("grounding"), "template lacks grounding"),
        (lambda s: s["utility"].update(system="3F-4H", nominal_voltage_v=220), "single-phase"),
        (lambda s: s["project"]["site"].update(t_min_c=-90), "project.site"),
    ],
)
def test_template_problems_are_reported_by_name(change: Any, message: str) -> None:
    spec = template()
    change(spec)
    with pytest.raises(SizingInputError, match=message):
        request_from_mapping({"template": spec, "module": ET_550})


def test_request_rejects_unknown_fields_and_inverted_ranges() -> None:
    with pytest.raises(SizingInputError, match="mdule"):
        request_from_mapping({"template": template(), "mdule": ET_550})
    with pytest.raises(SizingInputError, match="module_count_min"):
        request_from_mapping(
            {"template": template(), "module": ET_550, "module_count_min": 9, "module_count_max": 3}
        )


def test_candidate_severities_use_the_shared_enum() -> None:
    result = size(ET_550, [HUAWEI_5K], target_dc_power_w=9000)
    assert all(isinstance(i.severity, Severity) for c in result.candidates for i in c.issues)


# --- gPV fuse selection, the default of the DC protection box (owner decision 2026-10-08) ------


def test_a_gpv_fuse_disconnector_protects_each_string_by_default() -> None:
    result = size(JINKO_650, [GROWATT_5K], target_dc_power_w=9000)
    selected = result.selected
    assert selected is not None
    dc = selected.bos.dc_ocpd
    assert (dc.device, dc.device_id, dc.rating_a, dc.ue_v) == (
        "fuse",
        "LITTELFUSE-SPF030",
        30,
        1000,
    )
    assert dc.minimum_rating_a is not None
    assert dc.minimum_rating_a <= 30 <= 35  # >= 1.56 x Isc, <= the module's maximum series fuse
    disconnects = [d for d in result.spec["dc_bos"]["disconnects"] if not d["integrated_in"]]  # type: ignore[index]
    assert [d["id"] for d in disconnects] == ["FUS-S1", "FUS-S2", "DCD-CD1"]
    assert all(d["ie_a"] == 30 and d["poles"] == 2 for d in disconnects[:2])
    assert validate_selected(result).ok


def test_without_a_fitting_fuse_the_box_falls_back_to_a_breaker_and_says_why() -> None:
    result = size(JINKO_650, [GROWATT_5K], target_dc_power_w=9000, dc_fuses=["LITTELFUSE-SPF020"])
    selected = result.selected
    assert selected is not None
    dc = selected.bos.dc_ocpd
    assert (dc.device, dc.device_id) == ("breaker", "SUNTREE-SL7N-63-32A")
    assert "LITTELFUSE-SPF020: 20 A <" in dc.reason_es
    assert dc.reason_es.endswith("Se usa un ITM de CD.")
    disconnects = [d for d in result.spec["dc_bos"]["disconnects"] if not d["integrated_in"]]  # type: ignore[index]
    assert [d["id"] for d in disconnects] == ["DCB-S1", "DCB-S2", "DCD-CD1"]
