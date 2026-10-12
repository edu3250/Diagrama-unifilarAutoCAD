"""Stage 3.4: string OCPD, inverter-output breaker and conductors (vault worked examples)."""

from __future__ import annotations

import pytest

from pvsld.core.severity import Severity
from pvsld.core.tables import get_tables
from pvsld.sizing import bos
from sizing_helpers import ET_550, JINKO_650, SCHNEIDER_20A, registry

TABLES = get_tables("NOM-001-SEDE-2012")
SUNTREE = [c for c in registry().dc_breakers() if c.manufacturer == "Suntree"]
SCHNEIDER = [registry().get(SCHNEIDER_20A)]
BOTH = [*SUNTREE, *SCHNEIDER]


# --- Is a string OCPD needed? -----------------------------------------------------------------


@pytest.mark.parametrize("per_input", [1, 2])
def test_one_or_two_strings_per_input_need_no_string_ocpd(per_input: int) -> None:
    module = registry().get(JINKO_650)
    required, reason = bos.string_ocpd_required(module, 18.16, per_input)  # type: ignore[arg-type]
    assert not required
    assert "NOM 690-9(a)" in reason


def test_three_strings_per_input_need_a_string_ocpd_for_the_jinko_module() -> None:
    # (3 - 1) x 1.25 x 18.16 = 45.4 A > 35 A (module maximum series fuse)
    required, reason = bos.string_ocpd_required(registry().get(JINKO_650), 18.16, 3)  # type: ignore[arg-type]
    assert required
    assert "45.4 A" in reason
    assert "35 A" in reason


def test_three_strings_per_input_need_a_string_ocpd_for_the_et_module() -> None:
    # (3 - 1) x 1.25 x 14.04 = 35.1 A > 25 A
    required, _ = bos.string_ocpd_required(registry().get(ET_550), 14.04, 3)  # type: ignore[arg-type]
    assert required


# --- Which breaker? Suntree vs Schneider for the Jinko 650 W ----------------------------------


def _select(isc_a: float, voc_v: float, breakers: list, module_id: str = JINKO_650):  # type: ignore[type-arg]
    return bos.select_string_breaker(
        module=registry().get(module_id),  # type: ignore[arg-type]
        isc_a=isc_a,
        strings_per_input=1,
        voc_cold_string_v=voc_v,
        breakers=breakers,
        required=True,
        reason_es="por diseño",
    )


def test_schneider_20_a_is_undersized_for_the_jinko_650() -> None:
    # 1.25 x 1.25 x 16.44 A (STC) = 25.7 A: the owner's check; 28.4 A with the BNPI current
    choice = _select(16.44, 538.0, SCHNEIDER)
    assert choice.device_id is None
    assert choice.minimum_rating_a == pytest.approx(25.69, abs=0.01)
    assert "A9N61652" in choice.reason_es
    assert "20 A < 25.7 A" in choice.reason_es


def test_suntree_32_a_is_the_smallest_adequate_breaker() -> None:
    choice = _select(18.16, 538.0, BOTH)
    assert choice.device_id == "SUNTREE-SL7N-63-32A"
    assert choice.rating_a == 32
    assert choice.minimum_rating_a == pytest.approx(28.375)
    assert choice.poles == 2
    # smallest offered 2P rated voltage at or above Voc(T_min): 550 V; Icu from the 800 V entry
    assert choice.ue_v == 550
    assert choice.icu_ka == 6.0
    rejected = dict(choice.rejected)
    assert "SCHNEIDER-A9N61652" in rejected
    assert "SUNTREE-SL7N-63-25A" in rejected  # 25 A < 28.4 A


def test_boundary_rating_between_stc_and_bnpi_currents() -> None:
    # 25 A is enough for the STC current (25.7 A needs 32 A as well) but never for BNPI (28.4 A)
    assert _select(16.44, 538.0, SUNTREE).rating_a == 32
    assert _select(15.0, 538.0, SUNTREE).rating_a == 25  # 1.5625 x 15 = 23.4 A


def test_breaker_rating_cannot_exceed_the_module_series_fuse() -> None:
    # a module with a 30 A maximum series fuse and 28.4 A needed leaves 32 A out
    module = registry().get(JINKO_650).model_copy(update={"max_series_fuse_a": 30.0})
    choice = bos.select_string_breaker(
        module=module,  # type: ignore[arg-type]
        isc_a=18.16,
        strings_per_input=1,
        voc_cold_string_v=538.0,
        breakers=SUNTREE,
        required=True,
        reason_es="por diseño",
    )
    assert choice.device_id is None
    assert "32 A > 30 A" in choice.reason_es


def test_breaker_needs_a_rated_voltage_above_the_string_voltage() -> None:
    assert _select(18.16, 700.0, SUNTREE).ue_v == 800
    unavailable = _select(18.16, 850.0, SUNTREE)
    assert unavailable.device_id is None
    assert "850.0 V" in unavailable.reason_es


def test_breaking_capacity_follows_the_circuit_voltage() -> None:
    schneider_only = _select(10.0, 700.0, SCHNEIDER, module_id=ET_550)
    assert schneider_only.device_id == SCHNEIDER_20A
    assert schneider_only.icu_ka == 1.5  # 800 V entry for a 700 V circuit
    assert _select(10.0, 600.0, SCHNEIDER, module_id=ET_550).icu_ka == 3.0  # 650 V entry


def test_no_selection_when_the_ocpd_is_not_required() -> None:
    choice = bos.select_string_breaker(
        module=registry().get(JINKO_650),  # type: ignore[arg-type]
        isc_a=18.16,
        strings_per_input=1,
        voc_cold_string_v=538.0,
        breakers=BOTH,
        required=False,
        reason_es="No se requiere",
    )
    assert not choice.required
    assert choice.device_id is None


def test_an_empty_catalogue_explains_itself() -> None:
    choice = _select(18.16, 538.0, [])
    assert choice.device_id is None
    assert "catálogo sin interruptores" in choice.reason_es


# --- Inverter-output breaker ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("iac_a", "expected"),
    [(27.3, 35), (22.7, 30), (25.0, 35), (16.0, 20), (10.0, 15)],
)
def test_ac_breaker_is_the_next_standard_rating_above_125_percent(
    iac_a: float, expected: float
) -> None:
    assert bos.ac_ocpd_rating_a(iac_a, TABLES) == expected


# --- Conductors (vault: PV Conductor Sizing and Voltage Drop, worked example) -----------------


def _dc_drop(size: str) -> float:
    return 100 * (2 * 25 * 13.22 * TABLES.resistance_dc_ohm_km[size] / 1000) / 291.2


def test_dc_string_conductor_matches_the_vault_worked_example() -> None:
    choice, issues = bos.size_conductor(
        circuit_id="C-S",
        kind="pv_source",
        i_max_a=17.5,
        ocpd_a=None,
        current_carrying=4,
        ambient_c=38,
        clearance_mm=25,
        length_m=25,
        drop_pct=_dc_drop,
        drop_limit_pct=1.5,
        drop_rule="VD-001",
        tables=TABLES,
    )
    assert issues == []
    assert choice is not None
    assert choice.size == "10 AWG"  # 12 AWG: 30 x 0.71 x 0.80 = 17.0 A < 17.5 A
    assert choice.ampacity_corrected_a == pytest.approx(22.7, abs=0.05)
    assert choice.vd_pct == pytest.approx(0.92, abs=0.005)


def _ac_drop(size: str) -> float:
    return 100 * (2 * 30 * 27.3 * TABLES.resistance_ac_pvc_ohm_km[size] / 1000) / 220


def _ac(limit_pct: float):  # type: ignore[no-untyped-def]
    return bos.size_conductor(
        circuit_id="C-INV",
        kind="inverter_output",
        i_max_a=27.3,
        ocpd_a=35,
        current_carrying=2,
        ambient_c=35,
        clearance_mm=None,
        length_m=30,
        drop_pct=_ac_drop,
        drop_limit_pct=limit_pct,
        drop_rule="VD-002",
        tables=TABLES,
    )


def test_ac_conductor_is_8_awg_because_10_awg_fails_240_4_d() -> None:
    choice, issues = _ac(limit_pct=2.0)
    assert issues == []
    assert choice is not None
    assert choice.size == "8 AWG"
    assert choice.vd_pct == pytest.approx(1.91, abs=0.005)


def test_a_tighter_voltage_drop_limit_grows_the_ac_conductor() -> None:
    choice, _ = _ac(limit_pct=1.0)
    assert choice is not None
    assert choice.size == "4 AWG"  # vault: 6 AWG gives 1.20 %, 4 AWG 0.76 %
    assert choice.vd_pct == pytest.approx(0.76, abs=0.005)


def test_voltage_drop_that_no_size_meets_is_a_warning_with_the_largest_safe_size() -> None:
    choice, issues = bos.size_conductor(
        circuit_id="C-S",
        kind="pv_source",
        i_max_a=17.5,
        ocpd_a=None,
        current_carrying=2,
        ambient_c=30,
        clearance_mm=None,
        length_m=900,
        drop_pct=lambda size: (
            100 * (2 * 900 * 13.22 * TABLES.resistance_dc_ohm_km[size] / 1000) / 291.2
        ),
        drop_limit_pct=1.5,
        drop_rule="VD-001",
        tables=TABLES,
    )
    assert choice is not None
    assert choice.size == "4/0 AWG"
    assert [(i.rule_id, i.severity) for i in issues] == [("VD-001", Severity.WARNING)]


def test_a_current_no_copper_size_can_carry_is_an_error() -> None:
    choice, issues = bos.size_conductor(
        circuit_id="C-X",
        kind="pv_source",
        i_max_a=500,
        ocpd_a=None,
        current_carrying=2,
        ambient_c=30,
        clearance_mm=None,
        length_m=10,
        drop_pct=lambda size: 0.0,
        drop_limit_pct=1.5,
        drop_rule="VD-001",
        tables=TABLES,
    )
    assert choice is None
    assert [(i.rule_id, i.severity) for i in issues] == [("CON-002", Severity.ERROR)]


def test_an_ambient_with_no_ampacity_leaves_no_safe_size() -> None:
    choice, issues = bos.size_conductor(
        circuit_id="C-X",
        kind="pv_source",
        i_max_a=5,
        ocpd_a=None,
        current_carrying=2,
        ambient_c=95,
        clearance_mm=None,
        length_m=10,
        drop_pct=lambda size: 0.0,
        drop_limit_pct=1.5,
        drop_rule="VD-001",
        tables=TABLES,
    )
    assert choice is None
    assert issues[0].rule_id == "CON-002"


# --- Which gPV fuse? ------------------------------------------------------------------------------

SPF = [c for c in registry().dc_fuses() if c.manufacturer == "Littelfuse"]


def _fuse(**overrides: object) -> object:
    arguments: dict[str, object] = {
        "module": registry().get(ET_550),
        "isc_a": 14.04,
        "strings_per_input": 1,
        "voc_cold_string_v": 400.0,
        "fuses": SPF,
        "required": True,
        "reason_es": "Por diseño.",
    }
    return bos.select_string_fuse(**{**arguments, **overrides})  # type: ignore[arg-type]


def test_the_smallest_gpv_fuse_inside_the_window_wins() -> None:
    choice = _fuse()  # 1.25 x 1.25 x 14.04 = 21.9 A <= rating <= 25 A (module maximum)
    assert (choice.device, choice.device_id, choice.rating_a) == (  # type: ignore[attr-defined]
        "fuse",
        "LITTELFUSE-SPF025",
        25,
    )
    assert choice.icu_ka == 50  # type: ignore[attr-defined]
    reasons = dict(choice.rejected)  # type: ignore[attr-defined]
    assert reasons["LITTELFUSE-SPF020"].startswith("20 A < 21.9 A")
    assert reasons["LITTELFUSE-SPF030"].startswith("30 A > 25 A")


def test_no_gpv_fuse_rated_for_the_string_voltage_leaves_the_choice_empty() -> None:
    choice = _fuse(voc_cold_string_v=1100.0)
    assert choice.device_id is None  # type: ignore[attr-defined]
    assert "1000 V < 1100.0 V" in choice.reason_es  # type: ignore[attr-defined]


def test_no_fuse_is_chosen_when_no_string_protection_is_required() -> None:
    choice = _fuse(required=False)
    assert (choice.required, choice.device_id, choice.device) == (False, None, "fuse")  # type: ignore[attr-defined]
