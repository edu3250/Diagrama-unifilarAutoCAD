"""Stage 3.4b: EMT conduit fill (NOM Chapter 10, Tables 1, 4, 5 and 8; owner choices 2026-10-09)."""

from __future__ import annotations

from typing import Any

import pytest

from catalogue_helpers import REAL_RECORDS
from pvsld.catalogue import Cable, ComponentRegistry
from pvsld.core import calc
from pvsld.core.severity import Severity
from pvsld.core.tables import get_tables
from pvsld.core.validation import validate_pv_design
from pvsld.sizing import bos
from s1_helpers import mutated
from sizing_helpers import GROWATT_5K, JINKO_650, registry, size

TABLES = get_tables("NOM-001-SEDE-2012")


# --- The tables and the arithmetic --------------------------------------------------------------


def test_table_1_limits_the_fill_by_the_number_of_conductors() -> None:
    assert [calc.fill_limit_pct(n, TABLES) for n in (1, 2, 3, 9)] == [53, 31, 40, 40]


def test_table_4_emt_rows_agree_with_their_internal_diameter() -> None:
    for designation, _trade, diameter, area in TABLES.emt:
        assert calc.conductor_area_mm2(diameter) == pytest.approx(area, rel=0.01), designation
    assert [r[0] for r in TABLES.emt] == [16, 21, 27, 35, 41, 53, 63, 78, 91, 103]


def test_the_smallest_emt_is_the_first_within_the_fill() -> None:
    # Four 8 AWG THHW (5.994 mm) = 112.9 mm2, 40 %: 16 mm holds 78 mm2, 21 mm holds 137 mm2.
    area = calc.conductor_area_mm2(TABLES.thhw_diameter_mm["8 AWG"])
    designation, trade, pct = calc.smallest_emt([area] * 4, TABLES)  # type: ignore[misc]
    assert (designation, trade) == (21, "¾")
    assert pct == pytest.approx(4 * area / 343 * 100)


# --- Sizing ---------------------------------------------------------------------------------------


def _viakon(size_: str) -> Cable:
    return next(c for c in registry().cables() if c.size == size_)


def test_two_strings_of_viakon_pv_10_awg_need_a_27_mm_emt() -> None:
    # 4 x 7.1 mm PV wire (39.59 mm2 each) + bare 10 AWG (6.76 mm2) = 165.1 mm2, 5 conductors, 40 %:
    # 21 mm holds 137 mm2, 27 mm holds 222 mm2.
    choice, issues = bos.size_raceway(
        circuit_id="C-S",
        conductors=4,
        conductor_area_mm2=calc.conductor_area_mm2(_viakon("10 AWG").outer_diameter_mm),
        egc_size="10 AWG",
        given_trade_size_mm=None,
        insulation="PV 2 kV XLPE",
        tables=TABLES,
        cable=_viakon("10 AWG"),
    )
    assert issues == []
    assert (choice.trade_size_mm, choice.trade_size_in, choice.conductors) == (27, "1", 5)
    assert choice.area_mm2 == pytest.approx(4 * 39.592 + 6.76, abs=0.01)
    assert choice.fill_pct == pytest.approx(choice.area_mm2 / 556 * 100)
    assert choice.cable_id == "VIAKON-PV2000-10AWG"


def test_a_given_emt_too_small_is_an_error() -> None:
    _choice, issues = bos.size_raceway(
        circuit_id="C-S",
        conductors=4,
        conductor_area_mm2=calc.conductor_area_mm2(7.1),
        egc_size="10 AWG",
        given_trade_size_mm=21,
        insulation="PV",
        tables=TABLES,
    )
    assert [(i.rule_id, i.severity) for i in issues] == [("CON-006", Severity.ERROR)]
    assert "48.1 %" in issues[0].message_es


def test_without_the_cable_diameter_the_fill_is_a_warning() -> None:
    choice, issues = bos.size_raceway(
        circuit_id="C-S",
        conductors=4,
        conductor_area_mm2=None,
        egc_size="10 AWG",
        given_trade_size_mm=None,
        insulation="PV",
        tables=TABLES,
    )
    assert choice.trade_size_mm is None
    assert [(i.rule_id, i.severity) for i in issues] == [("CON-006", Severity.WARNING)]


def test_the_sized_spec_carries_emt_the_pv_cable_and_thhw_ls() -> None:
    result = size(JINKO_650, [GROWATT_5K], target_dc_power_w=9000)
    selected = result.selected
    assert selected is not None
    dc_raceway, ac_raceway = selected.bos.raceways
    assert (dc_raceway.type, ac_raceway.type) == ("EMT", "EMT")
    circuits = {c["id"]: c for c in result.spec["circuits"]}  # type: ignore[index]
    string = circuits["C-S1"]
    assert string["conductors"]["insulation"] == "PV 2 kV"
    assert (
        string["conductors"]["outer_diameter_mm"]
        == _viakon(string["conductors"]["size"]).outer_diameter_mm
    )
    assert string["raceway"]["type"] == "EMT"
    assert string["raceway"]["trade_size_mm"] == dc_raceway.trade_size_mm
    assert circuits["C-S2"]["raceway"] == {"ref": "C-S1"}
    assert circuits["C-INV"]["conductors"]["insulation"] == "THHW-LS"
    assert circuits["C-INV"]["raceway"]["trade_size_mm"] == ac_raceway.trade_size_mm
    report = validate_pv_design(result.spec)
    assert not [f for f in report.findings if f.rule_id == "CON-006"]


# --- Rule CON-006 ---------------------------------------------------------------------------------


def _emt(dc_mm: float, *, diameter: float | None = 7.1) -> Any:
    def change(spec: dict[str, Any]) -> None:
        for circuit in spec["circuits"]:
            if circuit["id"] == "C-S1":
                circuit["raceway"]["type"] = "EMT"
                circuit["raceway"]["trade_size_mm"] = dc_mm
            if circuit["kind"] == "pv_source":
                circuit["conductors"]["insulation"] = "PV 2 kV XLPE"
                if diameter is not None:
                    circuit["conductors"]["outer_diameter_mm"] = diameter

    return change


def test_con_006_flags_an_overfilled_emt_and_names_the_size_that_fits() -> None:
    findings = [f for f in validate_pv_design(mutated(_emt(21))).findings if f.rule_id == "CON-006"]
    assert [(f.severity, f.subject) for f in findings] == [(Severity.ERROR, "C-S1")]
    assert "C-S1, C-S2" in findings[0].message_es
    assert "use EMT de 27 mm" in findings[0].message_es


def test_con_006_passes_a_large_enough_emt() -> None:
    report = validate_pv_design(mutated(_emt(27)))
    assert not [f for f in report.findings if f.rule_id == "CON-006"]


def test_con_006_warns_when_a_cable_has_no_known_diameter() -> None:
    findings = [
        f
        for f in validate_pv_design(mutated(_emt(27, diameter=None))).findings
        if f.rule_id == "CON-006"
    ]
    assert [f.severity for f in findings] == [Severity.WARNING]
    assert "outer_diameter_mm" in findings[0].message_es


def test_the_viakon_record_loads_with_its_diameters() -> None:
    cables = ComponentRegistry.load(REAL_RECORDS, include_unreviewed=True).cables()
    by_size = {c.size: c for c in cables if c.family_id == "VIAKON-PV-WIRE-2000V"}
    assert by_size["10 AWG"].outer_diameter_mm == 7.1
    assert by_size["4/0 AWG"].outer_diameter_mm == 18.9
    assert all(c.application == "pv" and c.rated_voltage_v == 2000 for c in by_size.values())
