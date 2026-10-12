"""Stage 3.4b: ITM-1, ITM-P and the box disconnect from the catalogue (owner 2026-10-09)."""

from __future__ import annotations

from pvsld.core.severity import Severity
from pvsld.core.validation import validate_pv_design
from pvsld.sizing import bos
from sizing_helpers import GROWATT_5K, JINKO_650, registry, size

QO = registry().ac_breakers()
SISO = registry().dc_switches()


def test_the_next_qo_rating_up_with_enough_interrupting_rating_is_chosen() -> None:
    choice, issues = bos.select_ac_breaker(
        position="ITM-1", rating_a=32, poles=2, voltage_v=240, fault_ka=10, breakers=QO
    )
    assert issues == []
    assert choice is not None
    assert (choice.device_id, choice.rating_a, choice.interrupting_ka) == ("SQUARED-QO235", 35, 10)


def test_a_fault_current_above_10_ka_leaves_a_warning_and_no_device() -> None:
    choice, issues = bos.select_ac_breaker(
        position="ITM-1", rating_a=20, poles=2, voltage_v=240, fault_ka=22, breakers=QO
    )
    assert choice is None
    assert [(i.severity, i.subject) for i in issues] == [(Severity.WARNING, "ITM-1")]
    assert "SQUARED-QO220 interrumpe 10 kA" in issues[0].message_es


def test_the_main_breaker_keeps_its_rating() -> None:
    choice, _ = bos.select_ac_breaker(
        position="ITM-P",
        rating_a=100,
        poles=2,
        voltage_v=240,
        fault_ka=10,
        breakers=QO,
        exact=True,
    )
    assert choice is not None
    assert (choice.device_id, choice.rating_a) == ("SQUARED-QO2100", 100)
    none, issues = bos.select_ac_breaker(
        position="ITM-P",
        rating_a=95,
        poles=2,
        voltage_v=240,
        fault_ka=10,
        breakers=QO,
        exact=True,
    )
    assert none is None
    assert issues


def test_two_strings_use_two_poles_each_and_its_rating_falls_with_voltage() -> None:
    low, _ = bos.select_box_switch(
        position="DCD-CD1",
        n_strings=2,
        voc_cold_string_v=450,
        string_i_max_a=22.7,
        switches=SISO,
    )
    assert low is not None
    assert (low.device_id, low.rating_a, low.voltage_v) == ("SUNTREE-SISO-40-32", 32, 600)
    # At 900 V two poles per string carry 16 A only: too little for 22.7 A.
    high, issues = bos.select_box_switch(
        position="DCD-CD1",
        n_strings=2,
        voc_cold_string_v=900,
        string_i_max_a=22.7,
        switches=SISO,
    )
    assert high is None
    assert [i.severity for i in issues] == [Severity.WARNING]


def test_one_string_uses_the_four_poles_in_series() -> None:
    choice, _ = bos.select_box_switch(
        position="DCD-CD1",
        n_strings=1,
        voc_cold_string_v=900,
        string_i_max_a=22.7,
        switches=SISO,
    )
    assert choice is not None
    assert (choice.rating_a, choice.voltage_v) == (32, 1000)


def test_the_sized_spec_carries_the_catalogue_switchgear() -> None:
    result = size(JINKO_650, [GROWATT_5K], target_dc_power_w=9000)
    selected = result.selected
    assert selected is not None
    assert {d.position for d in selected.bos.devices} == {"ITM-1", "ITM-P", "DCD-CD1"}
    ac = result.spec["ac_bos"]  # type: ignore[index]
    itm = next(o for o in ac["ocpds"] if o["id"] == "ITM-1")
    assert itm["model"].startswith("SQUARED-QO2")
    assert itm["kaic_ka"] == 10
    main = ac["main_breakers"][0]
    assert (main["model"], main["kaic_ka"]) == ("SQUARED-QO2100", 10)
    box = next(d for d in result.spec["dc_bos"]["disconnects"] if d["id"] == "DCD-CD1")  # type: ignore[index]
    assert box["model"] == "SUNTREE-SISO-40-32"
    assert validate_pv_design(result.spec).ok
