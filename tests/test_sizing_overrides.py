"""Stage 3.6.2: values the user fixes in the professional mode are kept and checked, never replaced.

Baseline on the fixture catalogue: 8 x ETSOLAR 550 W on the Growatt MIN 5000TL-X2 gives 2 strings
of 4, gPV fuses SPF025, 8 AWG on both circuits, ITM-1 QO230 and ITM-P QO2100.
"""

from __future__ import annotations

from typing import Any

import pytest

from pvsld.sizing import SizingResult
from sizing_helpers import ET_550, GROWATT_5K, size, validate_selected

EIGHT = {"module_count_min": 8, "module_count_max": 8}


def _sized(**fields: Any) -> SizingResult:
    return size(ET_550, [GROWATT_5K], **{**EIGHT, **fields})


def _rules(result: SizingResult) -> set[str]:
    return {issue.rule_id for r in result.rejected for issue in r.issues}


def _messages(result: SizingResult, rule: str) -> list[str]:
    return [i.message_es for r in result.rejected for i in r.issues if i.rule_id == rule]


def test_the_baseline_the_overrides_change() -> None:
    selected = _sized().selected
    assert selected is not None
    assert (selected.config.n_strings, selected.config.n_series) == (2, 4)


def test_a_fixed_string_layout_is_the_only_one_evaluated() -> None:
    result = _sized(n_strings=1, n_series=8)
    assert result.selected is not None
    assert {(c.config.n_strings, c.config.n_series) for c in result.candidates} == {(1, 8)}
    assert validate_selected(result).ok


def test_a_fixed_string_count_beyond_the_inputs_is_rejected_with_the_reason() -> None:
    result = _sized(n_strings=5, n_series=2, module_count_min=10, module_count_max=10)
    assert result.selected is None
    assert "REQ-002" in _rules(result)
    assert "como máximo 2 cadena(s)" in _messages(result, "REQ-002")[0]


def test_a_fixed_series_count_that_breaks_a_rule_is_reported_not_replaced() -> None:
    result = _sized(n_series=1)
    assert result.selected is None
    assert {"STR-001", "REQ-001"} <= _rules(result)


@pytest.mark.parametrize(("field", "circuit"), [("dc_conductor_size", 0), ("ac_conductor_size", 1)])
def test_a_larger_fixed_conductor_size_is_used(field: str, circuit: int) -> None:
    selected = _sized(**{field: "6 AWG"}).selected
    assert selected is not None
    assert selected.bos.conductors[circuit].size == "6 AWG"


def test_a_fixed_conductor_too_small_is_an_error_naming_the_minimum() -> None:
    result = _sized(dc_conductor_size="14 AWG")
    assert result.selected is None
    messages = _messages(result, "CON-002")
    assert messages
    assert all("14 AWG fijado" in m and "el mínimo es" in m for m in messages)


def test_a_fixed_fuse_that_does_not_fit_is_an_error_not_a_breaker() -> None:
    result = _sized(dc_fuses=["LITTELFUSE-SPF015"], dc_fuse_fallback=False)
    assert result.selected is None
    assert "OCP-002" in _rules(result)


def test_by_default_a_fuse_that_does_not_fit_falls_back_to_a_breaker() -> None:
    selected = _sized(dc_fuses=["LITTELFUSE-SPF015"]).selected
    assert selected is not None
    assert selected.bos.dc_ocpd.device == "breaker"


def test_the_service_main_takes_the_fixed_catalogue_device() -> None:
    selected = _sized(main_breaker="SQUARED-QO2100", ac_breakers=["SQUARED-QO240"]).selected
    assert selected is not None
    devices = {d.position: d.device_id for d in selected.bos.devices}
    assert devices["ITM-P"] == "SQUARED-QO2100"
    assert devices["ITM-1"] == "SQUARED-QO240"  # restricting ITM-1 no longer hides ITM-P
