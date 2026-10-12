"""String configurations: enumerate them and check each against the module, inverter and site.

A configuration is ``n_strings`` identical strings of ``n_series`` modules on one inverter, spread
over its MPPTs round-robin (strings per MPPT <= ``inputs_per_mppt``). The checks use the same
formulas as :mod:`pvsld.core.calc` (vault notes "Temperature-Corrected Voc" and "PV String Sizing"):

========  ==========================================================  ========
Rule      Check                                                       Outcome
========  ==========================================================  ========
VOLT-001  Voc(T_min) of the string <= inverter max input voltage      reject
VOLT-002  Voc(T_min) of the string <= module max system voltage       reject
VOLT-003  Dwellings: Voc(T_min) of the string <= 600 V (NOM 690-7c)   reject
STR-001   Vmp(T_cell,max) of the string >= MPPT minimum voltage       reject
STR-002   Vmp(T_min) of the string <= MPPT maximum voltage            reject
STR-003   Vmp(T_cell,max) of the string >= start-up voltage           warn
STR-004   strings per MPPT x 1.25 x Isc <= max short-circuit current  reject
STR-005   strings per MPPT x Imp <= max input current (clipping)      warn
STR-007   array power <= inverter PV power limit; DC/AC policy        reject/warn
REQ-001   total modules inside the requested range                    reject
REQ-002   a string count the user fixed fits the inverter's inputs     reject
========  ==========================================================  ========

A string count or a modules-per-string value the user fixed (professional mode) pins the
enumeration to it, so its violations are reported instead of silently replaced.

STR-002 rejects here although the vault pack lists it as a warning: a string that cannot track
inside the MPPT window on cold mornings is not a design the engine proposes. ``Isc`` is the BNPI
value for a bifacial module (see :mod:`pvsld.sizing.adapters`); ``Imp`` for the clipping estimate
is the STC value, and the loss it reports is a peak (STC irradiance) figure, not an annual one.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass

from pvsld.catalogue import Inverter as CatalogueInverter
from pvsld.catalogue import PVModule as CatalogueModule
from pvsld.core import calc
from pvsld.core.calc import VocMethod
from pvsld.core.model import Module, Site
from pvsld.core.policy import DcAcPolicy
from pvsld.core.severity import Severity
from pvsld.sizing.adapters import design_isc_a
from pvsld.sizing.models import Issue, StringConfig, StringMetrics


def _n(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}"


def _g(value: float) -> str:
    return f"{value:g}"


@dataclass(frozen=True)
class EvalContext:
    """Everything a configuration is checked against."""

    module: CatalogueModule
    spec_module: Module
    inverter: CatalogueInverter
    site: Site
    voc_method: VocMethod
    cell_temp_rise_c: float
    optimizers_on_all_modules: bool
    policy: DcAcPolicy
    module_count_min: int | None = None
    module_count_max: int | None = None
    n_strings: int | None = None
    n_series: int | None = None

    @property
    def voc_cold_module_v(self) -> float:
        return calc.voc_max_module_v(self.spec_module, self.site.t_min_c, self.voc_method)

    @property
    def vmp_hot_module_v(self) -> float:
        t_cell = calc.t_cell_max_c(self.site.t_amb_max_c, self.cell_temp_rise_c)
        return calc.vmp_module_v(self.spec_module, t_cell)

    @property
    def voltage_ceiling_v(self) -> float:
        """Highest allowed Voc(T_min) of a string: inverter, module and dwelling limits."""
        ceiling = min(self.inverter.max_input_voltage_v, self.module.max_system_voltage_v)
        if self.site.occupancy.startswith("vivienda"):
            ceiling = min(ceiling, calc.DWELLING_VOLTAGE_LIMIT_V)
        return ceiling

    @property
    def max_strings(self) -> int:
        return self.inverter.mppt_count * self.inverter.inputs_per_mppt

    @property
    def n_max(self) -> int:
        """Most modules in series that keep Voc(T_min) under every voltage limit."""
        return math.floor(self.voltage_ceiling_v / self.voc_cold_module_v)

    @property
    def n_min_operating(self) -> int:
        """Fewest modules in series that keep the hot Vmp at or above the MPPT minimum."""
        return math.ceil(self.inverter.mppt_voltage_range_v[0] / self.vmp_hot_module_v)

    @property
    def pv_power_limit_w(self) -> float:
        return self.inverter.pv_power_limit_w(self.optimizers_on_all_modules)


@dataclass(frozen=True)
class Evaluation:
    """Metrics and issues of one configuration; it is a candidate when no issue is an error."""

    config: StringConfig
    metrics: StringMetrics
    issues: tuple[Issue, ...]

    @property
    def errors(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Issue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.WARNING)

    @property
    def feasible(self) -> bool:
        return not self.errors


def strings_per_mppt(inverter: CatalogueInverter, n_strings: int) -> list[int]:
    """Round-robin distribution of ``n_strings`` over the MPPTs, e.g. 3 over 2 -> [2, 1]."""
    base, extra = divmod(n_strings, inverter.mppt_count)
    return [base + (1 if index < extra else 0) for index in range(inverter.mppt_count)]


def enumerate_configs(ctx: EvalContext) -> Iterator[tuple[int, int]]:
    """``(n_strings, n_series)`` pairs: every string count, modules from just below the operating
    minimum to one above the voltage maximum (so the first violation of each bound is reported)."""
    low = max(1, ctx.n_min_operating - 1)
    high = max(low, ctx.n_max + 1)
    counts = [ctx.n_strings] if ctx.n_strings is not None else range(1, ctx.max_strings + 1)
    series = [ctx.n_series] if ctx.n_series is not None else range(low, high + 1)
    for n_strings in counts:
        for n_series in series:
            yield n_strings, n_series


def _clipping_pct(ctx: EvalContext, n_strings: int, n_series: int) -> float:
    """Share of the array's STC power lost to the MPPT current limit (0 when none is exceeded)."""
    module_w = ctx.module.pmax_w
    lost_w = 0.0
    for count in strings_per_mppt(ctx.inverter, n_strings):
        current_a = count * ctx.module.imp_a
        limit_a = ctx.inverter.max_input_current_per_mppt_a
        if count and current_a > limit_a:
            lost_w += count * n_series * module_w * (1 - limit_a / current_a)
    return 100 * lost_w / (n_strings * n_series * module_w)


def evaluate_config(ctx: EvalContext, n_strings: int, n_series: int) -> Evaluation:
    """Run every check of the module docstring on one configuration."""
    module, inverter, site = ctx.module, ctx.inverter, ctx.site
    inv_id = inverter.component_id
    config = StringConfig(inv_id, n_strings, n_series)
    label = config.label

    voc_cold = n_series * ctx.voc_cold_module_v
    vmp_hot = n_series * ctx.vmp_hot_module_v
    vmp_cold = calc.vmp_cold_string_v(ctx.spec_module, n_series, site.t_min_c)
    isc_a = design_isc_a(module)
    per_mppt = strings_per_mppt(inverter, n_strings)
    worst = max(per_mppt)
    isc_input = calc.isc_input_a(isc_a, worst)
    p_dc = n_strings * n_series * module.pmax_w
    ratio = p_dc / inverter.rated_ac_power_w
    clipping = _clipping_pct(ctx, n_strings, n_series)
    metrics = StringMetrics(
        p_dc_w=p_dc,
        dc_ac_ratio=ratio,
        voc_cold_string_v=voc_cold,
        vmp_hot_string_v=vmp_hot,
        vmp_cold_string_v=vmp_cold,
        isc_design_a=isc_a,
        isc_input_a=isc_input,
        imp_a=module.imp_a,
        strings_per_mppt=worst,
        clipping_pct=clipping,
        deliverable_dc_w=p_dc * (1 - clipping / 100),
    )

    issues: list[Issue] = []
    err, warn = Severity.ERROR, Severity.WARNING

    def add(rule: str, severity: Severity, text: str) -> None:
        issues.append(Issue(rule, severity, text, subject=f"{inv_id} {label}"))

    t_min = _g(site.t_min_c)
    reach = f"(máximo {ctx.n_max} módulos en serie)"
    if voc_cold > inverter.max_input_voltage_v:
        add(
            "VOLT-001",
            err,
            f"Con {n_series} módulos en serie la rama alcanza {_n(voc_cold)} V a {t_min} °C; el "
            f"inversor {inv_id} admite {_g(inverter.max_input_voltage_v)} V {reach}.",
        )
    if voc_cold > module.max_system_voltage_v:
        add(
            "VOLT-002",
            err,
            f"Con {n_series} módulos en serie la rama alcanza {_n(voc_cold)} V a {t_min} °C; el "
            f"módulo admite {_g(module.max_system_voltage_v)} V de tensión máxima del sistema.",
        )
    if site.occupancy.startswith("vivienda") and voc_cold > calc.DWELLING_VOLTAGE_LIMIT_V:
        add(
            "VOLT-003",
            err,
            f"Con {n_series} módulos en serie la rama alcanza {_n(voc_cold)} V a {t_min} °C; en "
            f"vivienda el límite es {_g(calc.DWELLING_VOLTAGE_LIMIT_V)} V (NOM 690-7(c)).",
        )

    low_v, high_v = inverter.mppt_voltage_range_v
    t_cell = _g(calc.t_cell_max_c(site.t_amb_max_c, ctx.cell_temp_rise_c))
    if vmp_hot < low_v:
        add(
            "STR-001",
            err,
            f"Con {n_series} módulos en serie la rama entrega {_n(vmp_hot)} V con celdas a "
            f"{t_cell} °C; el MPPT del inversor {inv_id} arranca en {_g(low_v)} V "
            f"(mínimo {ctx.n_min_operating} módulos).",
        )
    if vmp_cold > high_v:
        add(
            "STR-002",
            err,
            f"Con {n_series} módulos en serie la rama entrega {_n(vmp_cold)} V (Vmp) a {t_min} °C; "
            f"el MPPT del inversor {inv_id} llega a {_g(high_v)} V.",
        )
    elif low_v <= vmp_hot < inverter.startup_voltage_v:
        add(
            "STR-003",
            warn,
            f"La rama de {n_series} módulos entrega {_n(vmp_hot)} V con celdas a {t_cell} °C, "
            f"por debajo de los {_g(inverter.startup_voltage_v)} V de arranque del inversor "
            f"{inv_id}: puede tardar en conectarse en días calurosos.",
        )

    if isc_input > inverter.max_short_circuit_current_per_mppt_a:
        source = "BNPI (bifacial)" if module.bnpi is not None else "STC"
        bare = f"; sin el factor 1.25 serían {_n(worst * isc_a, 2)} A"
        add(
            "STR-004",
            err,
            f"El MPPT del inversor {inv_id} recibiría {worst} rama(s) con {_n(isc_input, 2)} A de "
            f"cortocircuito (1.25 × {_n(isc_a, 2)} A {source} por rama){bare}; el límite del "
            f"inversor es {_g(inverter.max_short_circuit_current_per_mppt_a)} A por MPPT.",
        )
    if clipping > 0:
        bifacial = (
            f"; con la ganancia bifacial (BNPI) llegaría a {_n(worst * module.bnpi.imp_a, 2)} A"
            if module.bnpi is not None
            else ""
        )
        add(
            "STR-005",
            warn,
            f"El MPPT del inversor {inv_id} recibiría {_n(worst * module.imp_a, 2)} A de Imp "
            f"({worst} rama(s) × {_n(module.imp_a, 2)} A){bifacial}; su corriente máxima de "
            f"entrada es {_g(inverter.max_input_current_per_mppt_a)} A. Recorte estimado: "
            f"{_n(clipping)} % de la potencia pico (STC).",
        )

    limit_w = ctx.pv_power_limit_w
    ac_kw = _n(inverter.rated_ac_power_w / 1000, 2)
    array = f"El arreglo de {n_strings * n_series} módulos suma {_n(p_dc / 1000, 2)} kWp (STC)"
    if p_dc > limit_w:
        add(
            "STR-007",
            err,
            f"{array}; el inversor {inv_id} admite como máximo {_n(limit_w / 1000, 2)} kWp "
            f"(relación CD/CA {_n(ratio, 2)} sobre {ac_kw} kW CA).",
        )
    else:
        severity = ctx.policy.classify(ratio)
        if severity is Severity.ERROR:
            add(
                "STR-007",
                err,
                f"{array} sobre {ac_kw} kW CA: la relación CD/CA es {_n(ratio, 2)}, por encima del "
                f"máximo de diseño {_n(ctx.policy.error_above, 2)}.",
            )
        elif severity is Severity.WARNING:
            add(
                "STR-007",
                warn,
                f"{array} sobre {ac_kw} kW CA: la relación CD/CA es {_n(ratio, 2)}, por encima de "
                f"{_n(ctx.policy.warn_above, 2)}; habrá recorte de potencia.",
            )
        elif severity is Severity.INFO:
            add(
                "STR-007",
                Severity.INFO,
                f"{array} sobre {ac_kw} kW CA: la relación CD/CA es {_n(ratio, 2)}, menor que "
                f"{_n(ctx.policy.info_below, 2)}.",
            )

    if n_strings > ctx.max_strings:
        add(
            "REQ-002",
            err,
            f"El inversor {inv_id} admite como máximo {ctx.max_strings} cadena(s) "
            f"({inverter.mppt_count} MPPT × {inverter.inputs_per_mppt} entrada(s)); se pidieron "
            f"{n_strings}.",
        )
    total = n_strings * n_series
    if ctx.module_count_min is not None and total < ctx.module_count_min:
        add(
            "REQ-001",
            err,
            f"{total} módulos son menos que el mínimo solicitado ({ctx.module_count_min}).",
        )
    if ctx.module_count_max is not None and total > ctx.module_count_max:
        add(
            "REQ-001",
            err,
            f"{total} módulos son más que el máximo solicitado ({ctx.module_count_max}).",
        )
    return Evaluation(config, metrics, tuple(issues))
