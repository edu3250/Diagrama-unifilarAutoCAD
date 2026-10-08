"""STR-007: array STC power within the inverter PV power limit, and the DC/AC ratio policy."""

from __future__ import annotations

from typing import Any

import pytest

from pvsld.core.policy import (
    DEFAULT_DC_AC_ERROR_ABOVE,
    DEFAULT_DC_AC_WARN_ABOVE,
    DcAcPolicy,
)
from pvsld.core.rules import Finding, Severity
from pvsld.core.validation import ValidationReport, validate_pv_design
from s1_helpers import load_example, mutated


def _modules_per_string(n: int, *, pdc_max_w: float | None = None) -> dict[str, Any]:
    def change(spec: dict[str, Any]) -> None:
        for string in spec["strings"]:
            string["n_series"] = n
        if pdc_max_w is not None:
            spec["inverters"][0]["pdc_max_w"] = pdc_max_w

    return mutated(change)


def _str_007(report: ValidationReport) -> list[Finding]:
    return [f for f in report.findings if f.rule_id == "STR-007"]


def test_default_policy_values_are_the_documented_ones() -> None:
    assert DEFAULT_DC_AC_WARN_ABOVE == 1.35
    assert DEFAULT_DC_AC_ERROR_ABOVE == 1.50


def test_sample_two_by_seven_passes_with_no_str_007_finding() -> None:
    report = validate_pv_design(load_example())
    assert report.ok
    assert _str_007(report) == []


def test_array_exactly_at_the_inverter_limit_is_accepted() -> None:
    # 2 x 7 x 550 W = 7700 W against a 7700 W limit: "<=" holds; ratio 1.283 is inside the policy.
    report = validate_pv_design(_modules_per_string(7, pdc_max_w=7700))
    assert _str_007(report) == []


def test_array_just_over_the_inverter_limit_is_an_error() -> None:
    report = validate_pv_design(_modules_per_string(7, pdc_max_w=7699))
    (finding,) = _str_007(report)
    assert finding.severity is Severity.ERROR
    assert not report.ok


def test_phase_2_owner_test_two_by_eleven_is_rejected_by_str_007() -> None:
    # 2 x 11 x 550 W = 12.1 kWp against pdc_max_w 9 kW (Phase 2 manual test, S3).
    report = validate_pv_design(_modules_per_string(11))
    assert not report.ok
    (finding,) = _str_007(report)
    assert finding.severity is Severity.ERROR
    assert finding.subject == "INV1"
    assert "12.10 kWp" in finding.message_es
    assert "9.00 kW" in finding.message_es
    assert "2.02" in finding.message_es  # DC/AC ratio on 6 kW
    assert "INV1" in finding.message_es
    assert any("110-3(b)" in str(c) for c in finding.cites)
    # the other rules stay quiet: 586.8 V is below 600 V
    assert {f.rule_id for f in report.findings if f.severity is Severity.ERROR} == {"STR-007"}


def test_two_by_eight_is_valid_with_a_dc_ac_warning() -> None:
    # 8.8 kWp <= 9 kW, but 8.8 / 6 = 1.47 > 1.35 (owner example of the plan, Stage 3.4).
    report = validate_pv_design(_modules_per_string(8))
    assert report.ok
    (finding,) = _str_007(report)
    assert finding.severity is Severity.WARNING
    assert "1.47" in finding.message_es
    assert "1.35" in finding.message_es


def test_ratio_above_the_error_ceiling_is_an_error_even_within_the_datasheet_limit() -> None:
    # 2 x 9 x 550 = 9.9 kWp, limit raised to 12 kW: ratio 1.65 > 1.50.
    report = validate_pv_design(_modules_per_string(9, pdc_max_w=12000))
    (finding,) = _str_007(report)
    assert finding.severity is Severity.ERROR
    assert "1.65" in finding.message_es
    assert "1.50" in finding.message_es


@pytest.mark.parametrize(
    ("policy", "expected"),
    [
        (DcAcPolicy(warn_above=1.60, error_above=1.80), None),
        (DcAcPolicy(warn_above=1.30, error_above=1.40), Severity.ERROR),
        (DcAcPolicy(warn_above=1.30, error_above=1.60), Severity.WARNING),
    ],
)
def test_policy_thresholds_are_configurable(policy: DcAcPolicy, expected: Severity | None) -> None:
    report = validate_pv_design(_modules_per_string(8), dc_ac_policy=policy)
    severities = [f.severity for f in _str_007(report)]
    assert severities == ([expected] if expected else [])


def test_one_finding_per_inverter_when_power_and_ratio_both_fail() -> None:
    assert len(_str_007(validate_pv_design(_modules_per_string(11)))) == 1


def test_undersized_array_gets_an_info_finding() -> None:
    # 2 x 4 x 550 W = 4.4 kWp on 6 kW: ratio 0.73 < 1.0
    (finding,) = _str_007(validate_pv_design(_modules_per_string(4)))
    assert finding.severity is Severity.INFO
    assert "0.73" in finding.message_es


def test_limit_scales_with_the_number_of_identical_inverters() -> None:
    def two_inverters(spec: dict[str, Any]) -> None:
        for string in spec["strings"]:
            string["n_series"] = 11
        spec["inverters"][0]["qty"] = 2

    # 12.1 kWp on 2 x 9 kW and 2 x 6 kW: ratio 1.008, inside the policy
    assert _str_007(validate_pv_design(mutated(two_inverters))) == []


def test_policy_rejects_inconsistent_thresholds() -> None:
    with pytest.raises(ValueError, match="warn_above <= error_above"):
        DcAcPolicy(warn_above=1.6, error_above=1.4)


def test_policy_classify_boundaries_are_exclusive() -> None:
    policy = DcAcPolicy()
    assert policy.classify(1.35) is None
    assert policy.classify(1.3501) is Severity.WARNING
    assert policy.classify(1.50) is Severity.WARNING
    assert policy.classify(1.5001) is Severity.ERROR
    assert policy.classify(1.0) is None
    assert policy.classify(0.99) is Severity.INFO
