"""Balance of system v1: string overcurrent protection, inverter-output breaker and conductors.

Sources (vault notes "PV Overcurrent Protection and Disconnects" and "PV Conductor Sizing and
Voltage Drop", NOM-001-SEDE-2012; tables in :mod:`pvsld.core.tables`):

* **String OCPD needed?** NOM 690-9(a): none when the other sources cannot push more than the
  module's maximum series fuse through a string, practical test ``(N_p - 1) x 1.25 x Isc >
  max_series_fuse``. With one or two strings per MPPT input that never happens for a compliant
  module, so no string breaker is selected ("none for <= 2 strings per input"). The designer can
  ask for one per string anyway (``dc_ocpd: always``).
* **String breaker.** ``rating >= 1.25 x 1.25 x Isc`` (690-8(b)(1) on the 690-8(a)(1) current),
  ``rating <= max series fuse`` of the module, a rated voltage at or above Voc(T_min) of the string
  (the smallest offered one is chosen) and a breaking capacity from
  ``DcBreaker.breaking_capacity_ka(poles, voltage)``. The smallest adequate rating wins.
* **String fuse (gPV).** The default device of the DC protection box (owner decision 2026-10-08),
  in a two-pole fuse-disconnector: the same current window as the breaker (``>= 1.56 x Isc``, which
  is also the manufacturer's rule for ganged holders, ``<= max series fuse``), a rated voltage at or
  above Voc(T_min) and an interrupting rating above the fault current. The smallest wins.
* **Inverter-output OCPD.** The next standard rating (240-6(a)) >= 1.25 x the inverter's maximum
  AC current (690-8(b)(1)).
* **Conductors** (copper, 75 and 90 degC columns of Table 310-15(b)(16); the tables of
  ``pvsld.core.tables`` carry the "verify before real use" warning of that module). The smallest
  size with: ampacity at 75 degC >= 1.25 x I_max (CON-001), ampacity at 90 degC after temperature
  and bundling corrections >= I_max (CON-002), protected by its OCPD per 240-4(b)/(d) (CON-003,
  AC only), and a voltage drop within the project limit (VD-001/VD-002).

TODO Stage 3.4b: EGC per Table 250-122 (the EGC is set to the circuit conductor size), conduit
fill (CON-006), external DC disconnects for inverters without an integrated switch (DIS-001),
inverter maximum OCPD (OCP-005), aluminium conductors and multiple inverters.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pvsld.catalogue import DcBreaker, DcFuse
from pvsld.catalogue import PVModule as CatalogueModule
from pvsld.core import calc
from pvsld.core.severity import Severity
from pvsld.core.tables import NomTables
from pvsld.sizing.models import ConductorChoice, DcOcpdChoice, Issue

STRING_BREAKER_POLES = 2
"""A string is a two-wire circuit: both conductors are opened (ungrounded array, NOM 690-35)."""
STRING_FUSE_POLES = 2
"""One gPV fuse per conductor of the string, in a two-pole fuse-disconnector."""
LARGEST_SIZE = "4/0 AWG"

TODO_STAGE_3_4B = (
    "EGC igual al calibre del conductor del circuito (Tabla 250-122 pendiente).",
    "Diámetro de la canalización no calculado (CON-006, relleno de tubería, pendiente).",
    "Desconectador de CD externo si el inversor no lo integra (DIS-001, pendiente).",
    "Protección máxima de salida del inversor del fabricante (OCP-005, pendiente).",
)


def _n(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}"


def _g(value: float) -> str:
    return f"{value:g}"


# --- String overcurrent protection -------------------------------------------------------------


def string_ocpd_required(
    module: CatalogueModule, isc_a: float, strings_per_input: int
) -> tuple[bool, str]:
    """NOM 690-9(a) practical test: ``(N_p - 1) x 1.25 x Isc > max_series_fuse`` -> OCPD needed."""
    backfeed_a = (strings_per_input - 1) * calc.ISC_SAFETY_FACTOR * isc_a
    limit_a = module.max_series_fuse_a
    if backfeed_a > limit_a:
        return True, (
            f"({strings_per_input} - 1) × 1.25 × {_n(isc_a, 2)} A = {_n(backfeed_a)} A supera el "
            f"fusible máximo del módulo ({_g(limit_a)} A): se requiere protección por rama "
            f"(NOM 690-9(a))."
        )
    if strings_per_input == 1:
        return False, (
            "No se requiere: una sola rama por entrada de MPPT, sin fuentes en paralelo "
            "(NOM 690-9(a))."
        )
    return False, (
        f"No se requiere: ({strings_per_input} - 1) × 1.25 × {_n(isc_a, 2)} A = "
        f"{_n(backfeed_a)} A no supera el fusible máximo del módulo ({_g(limit_a)} A) "
        f"(NOM 690-9(a); con 1 o 2 ramas por entrada no se requiere)."
    )


def select_string_breaker(
    *,
    module: CatalogueModule,
    isc_a: float,
    strings_per_input: int,
    voc_cold_string_v: float,
    breakers: Sequence[DcBreaker],
    required: bool,
    reason_es: str,
) -> DcOcpdChoice:
    """Choose the smallest catalogue breaker that satisfies the criteria of the module docstring.

    When ``required`` is false nothing is selected. When it is true and no breaker qualifies the
    returned choice has ``device_id`` ``None`` and ``reason_es`` explains each exclusion.
    """
    if not required:
        return DcOcpdChoice(required=False, reason_es=reason_es)
    minimum_a = calc.ocpd_min_a(calc.ISC_SAFETY_FACTOR * isc_a)
    maximum_a = module.max_series_fuse_a
    fault_a = strings_per_input * isc_a
    qualified: list[tuple[float, float, str, DcBreaker, float]] = []
    rejected: list[tuple[str, str]] = []
    for breaker in sorted(breakers, key=lambda b: b.component_id):
        name = breaker.component_id
        if breaker.rated_current_a < minimum_a:
            rejected.append(
                (name, f"{_g(breaker.rated_current_a)} A < {_n(minimum_a)} A (1.25 × 1.25 × Isc)")
            )
            continue
        if breaker.rated_current_a > maximum_a:
            rejected.append(
                (name, f"{_g(breaker.rated_current_a)} A > {_g(maximum_a)} A (fusible máximo)")
            )
            continue
        voltages = [v for v in breaker.ue_options_v(STRING_BREAKER_POLES) if v >= voc_cold_string_v]
        if not voltages:
            rejected.append(
                (
                    name,
                    f"sin tensión nominal >= {_n(voc_cold_string_v)} V en {STRING_BREAKER_POLES}P",
                )
            )
            continue
        ue_v = min(voltages)
        icu_ka = breaker.breaking_capacity_ka(STRING_BREAKER_POLES, voc_cold_string_v)
        if icu_ka is None or icu_ka * 1000 < fault_a:
            shown = "sin dato" if icu_ka is None else f"{_g(icu_ka)} kA"
            rejected.append((name, f"capacidad de ruptura {shown} < {_n(fault_a)} A de falla"))
            continue
        qualified.append((breaker.rated_current_a, ue_v, name, breaker, icu_ka))
    if not qualified:
        details = (
            "; ".join(f"{name}: {why}" for name, why in rejected) or "catálogo sin interruptores"
        )
        return DcOcpdChoice(
            required=True,
            reason_es=(
                f"{reason_es} Ningún interruptor de CD del catálogo cumple "
                f"(>= {_n(minimum_a)} A, <= {_g(maximum_a)} A, >= {_n(voc_cold_string_v)} V): "
                f"{details}."
            ),
            minimum_rating_a=minimum_a,
            rejected=tuple(rejected),
        )
    rating, ue_v, name, breaker, icu_ka = min(qualified, key=lambda q: q[:3])
    return DcOcpdChoice(
        required=True,
        reason_es=reason_es,
        device_id=name,
        rating_a=rating,
        ue_v=ue_v,
        poles=STRING_BREAKER_POLES,
        icu_ka=icu_ka,
        minimum_rating_a=minimum_a,
        rejected=tuple(rejected),
    )


def select_string_fuse(
    *,
    module: CatalogueModule,
    isc_a: float,
    strings_per_input: int,
    voc_cold_string_v: float,
    fuses: Sequence[DcFuse],
    required: bool,
    reason_es: str,
) -> DcOcpdChoice:
    """Choose the smallest catalogue gPV fuse that satisfies the criteria of the module docstring.

    Like :func:`select_string_breaker`: nothing when ``required`` is false, ``device_id`` ``None``
    with every exclusion in ``reason_es`` when no fuse qualifies.
    """
    if not required:
        return DcOcpdChoice(required=False, reason_es=reason_es, device="fuse")
    minimum_a = calc.ocpd_min_a(calc.ISC_SAFETY_FACTOR * isc_a)
    maximum_a = module.max_series_fuse_a
    fault_a = strings_per_input * isc_a
    qualified: list[tuple[float, str, DcFuse]] = []
    rejected: list[tuple[str, str]] = []
    for fuse in sorted(fuses, key=lambda f: f.component_id):
        name = fuse.component_id
        if fuse.rated_current_a < minimum_a:
            why = f"{_g(fuse.rated_current_a)} A < {_n(minimum_a)} A (1.25 × 1.25 × Isc)"
        elif fuse.rated_current_a > maximum_a:
            why = f"{_g(fuse.rated_current_a)} A > {_g(maximum_a)} A (fusible máximo)"
        elif fuse.rated_voltage_v < voc_cold_string_v:
            why = f"{_g(fuse.rated_voltage_v)} V < {_n(voc_cold_string_v)} V"
        elif fuse.breaking_capacity_ka * 1000 < fault_a:
            why = f"capacidad interruptiva {_g(fuse.breaking_capacity_ka)} kA < {_n(fault_a)} A"
        else:
            qualified.append((fuse.rated_current_a, name, fuse))
            continue
        rejected.append((name, why))
    if not qualified:
        details = "; ".join(f"{name}: {why}" for name, why in rejected) or "catálogo sin fusibles"
        return DcOcpdChoice(
            required=True,
            reason_es=(
                f"{reason_es} Ningún fusible gPV del catálogo cumple "
                f"(>= {_n(minimum_a)} A, <= {_g(maximum_a)} A, >= {_n(voc_cold_string_v)} V): "
                f"{details}."
            ),
            device="fuse",
            minimum_rating_a=minimum_a,
            rejected=tuple(rejected),
        )
    rating, name, fuse = min(qualified, key=lambda q: q[:2])
    return DcOcpdChoice(
        required=True,
        reason_es=reason_es,
        device_id=name,
        device="fuse",
        rating_a=rating,
        ue_v=fuse.rated_voltage_v,
        poles=STRING_FUSE_POLES,
        icu_ka=fuse.breaking_capacity_ka,
        minimum_rating_a=minimum_a,
        rejected=tuple(rejected),
    )


# --- Inverter-output OCPD ----------------------------------------------------------------------


def ac_ocpd_rating_a(iac_max_a: float, tables: NomTables) -> float:
    """Next standard rating >= 1.25 x the inverter's maximum AC current (690-8(b)(1), 240-6(a))."""
    return calc.next_standard_ocpd_a(calc.ocpd_min_a(iac_max_a), tables)


# --- Conductors ---------------------------------------------------------------------------------


def size_conductor(
    *,
    circuit_id: str,
    kind: str,
    i_max_a: float,
    ocpd_a: float | None,
    current_carrying: int,
    ambient_c: float,
    clearance_mm: float | None,
    length_m: float,
    drop_pct: Callable[[str], float],
    drop_limit_pct: float,
    drop_rule: str,
    tables: NomTables,
) -> tuple[ConductorChoice | None, list[Issue]]:
    """Smallest copper size that satisfies ampacity, protection and voltage drop for one circuit.

    ``drop_pct(size)`` returns the voltage drop in percent for a size. Returns ``(None, [error])``
    when no size up to 4/0 AWG is safe, and a warning (with the largest size) when only the voltage
    drop cannot be met.
    """
    adder = calc.rooftop_adder_c(clearance_mm, tables) if clearance_mm is not None else 0.0
    t_effective = ambient_c + adder
    k_temp = calc.temperature_correction(t_effective, tables)
    k_fill = calc.bundling_factor(current_carrying, tables)
    safe: list[tuple[str, float, float]] = []
    for size in tables.ampacity_cu:
        a75 = calc.ampacity_a(size, 75, tables)
        a90 = calc.ampacity_a(size, 90, tables)
        corrected = a90 * k_temp * k_fill
        if a75 < calc.ocpd_min_a(i_max_a) or corrected < i_max_a:
            continue
        if ocpd_a is not None:
            limit = calc.max_ocpd_for_ampacity_a(min(a75, corrected), tables)
            small = tables.small_conductor_ocpd_limit_a.get(size)
            if ocpd_a > limit or (small is not None and ocpd_a > small):
                continue
        safe.append((size, a75, corrected))
    if not safe:
        return None, [
            Issue(
                "CON-002",
                Severity.ERROR,
                f"Ningún calibre de cobre hasta {LARGEST_SIZE} soporta {_n(i_max_a)} A en el "
                f"circuito {circuit_id} a {_g(t_effective)} °C con {current_carrying} conductores "
                f"(factores {_n(k_temp, 2)} y {_n(k_fill, 2)}).",
                subject=circuit_id,
            )
        ]
    issues: list[Issue] = []
    chosen = next((c for c in safe if drop_pct(c[0]) <= drop_limit_pct), None)
    if chosen is None:
        chosen = safe[-1]
        issues.append(
            Issue(
                drop_rule,
                Severity.WARNING,
                f"La caída de tensión del circuito {circuit_id} ({_n(drop_pct(chosen[0]), 2)} %) "
                f"excede el límite de {_n(drop_limit_pct, 2)} % incluso con {chosen[0]} a "
                f"{_g(length_m)} m; acorte el recorrido o suba la tensión.",
                subject=circuit_id,
            )
        )
    size, a75, corrected = chosen
    return (
        ConductorChoice(
            circuit_id=circuit_id,
            kind=kind,
            size=size,
            i_max_a=i_max_a,
            ocpd_a=ocpd_a,
            ampacity_75_a=a75,
            ampacity_corrected_a=corrected,
            vd_pct=drop_pct(size),
            vd_limit_pct=drop_limit_pct,
            length_m=length_m,
        ),
        issues,
    )
