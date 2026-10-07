"""Inverter records: one family (values common to the models) with one variant per model.

Datasheets of an inverter series print one column per model. The columns that do not change (MPPT
count and currents, grid, certifications) live once on the family; every model keeps its own power
ratings and gets its own ``component_id``. The input voltage limits (``max_input_voltage_v`` and
``mppt_voltage_range_v``) differ by model on some series (Growatt MIN: 500 V on the 2500 and 3000,
550 V on the rest), so a record defines each of them at exactly one level, family or variant; the
expanded :class:`Inverter` always carries the resolved value.

STR-007 (inverter DC power) uses :meth:`InverterVariant.pv_power_limit_w`. A datasheet may publish
a higher PV power that is only allowed with module-level optimizers (Huawei footnote "10,000 Wp
with optimizers"); it is stored only on the model the datasheet attaches it to, flagged ambiguous
when the datasheet does not say whether the other models share it, and used only when the design
declares optimizers on every module.
"""

from __future__ import annotations

import math
from typing import Annotated, Literal

from pydantic import AfterValidator, Field, model_validator

from pvsld.catalogue.common import (
    ComponentId,
    Percent,
    PositiveFloat,
    PositiveInt,
    Provenance,
    Range,
    Strict,
    check_range,
    duplicates,
    has_certification,
    raise_problems,
)

# S = V x I (x sqrt 3) must hold within this tolerance at one of the rated AC voltages. Growatt
# prints its maximum current for 220 V while listing 230 V as nominal, hence 5 % and not less.
AC_CURRENT_TOLERANCE = 0.05
Grid = Literal["single_phase", "split_phase", "three_phase"]


def _ascending_range(value: Range) -> Range:
    problem = check_range("range", value)
    if problem:
        raise ValueError(problem)
    return value


def _power_factor_range(value: Range) -> Range:
    problem = check_range("power_factor_range", value, allow_equal=True)
    if problem:
        raise ValueError(problem)
    if value[0] < -1 or value[1] > 1:
        raise ValueError(f"power_factor_range {value} must stay within [-1, 1]")
    return value


AscendingRange = Annotated[Range, AfterValidator(_ascending_range)]
PowerFactorRange = Annotated[Range, AfterValidator(_power_factor_range)]


class BatteryPort(Strict):
    """DC port for a battery (hybrid inverters)."""

    compatible: str | None = Field(default=None, description="Compatible battery series")
    voltage_range_v: AscendingRange
    max_current_a: PositiveFloat
    max_charge_power_w: PositiveFloat

    @model_validator(mode="after")
    def _plausible(self) -> BatteryPort:
        ceiling = self.voltage_range_v[1] * self.max_current_a
        if self.max_charge_power_w > ceiling:
            raise ValueError(
                f"max_charge_power_w ({self.max_charge_power_w:g}) exceeds the highest battery "
                f"voltage x max_current_a ({ceiling:g} W)"
            )
        return self


class InverterProtection(Strict):
    """Built-in protections as listed on the datasheet (``None`` = not stated)."""

    anti_islanding: bool | None = None
    dc_reverse_polarity: bool | None = None
    dc_switch: bool | None = None
    insulation_monitoring: bool | None = None
    residual_current_monitoring: bool | None = None
    grid_monitoring: bool | None = None
    ac_short_circuit: bool | None = None
    arc_fault: bool | None = None
    afci: bool | None = None
    dc_spd: str | None = None
    ac_spd: str | None = None


class InverterVariant(Strict):
    """One inverter model of the family (one column of the datasheet table)."""

    component_id: ComponentId
    max_input_voltage_v: PositiveFloat | None = Field(
        default=None, description="Per-model value; omit it when the family defines it"
    )
    mppt_voltage_range_v: AscendingRange | None = Field(
        default=None, description="Per-model value; omit it when the family defines it"
    )
    recommended_max_pv_power_wp: PositiveFloat = Field(
        description="Recommended maximum PV input power; STR-007 uses it as P_dc,max"
    )
    max_pv_power_with_optimizers_wp: PositiveFloat | None = Field(
        default=None,
        description="Higher PV power allowed only with optimizers on every module",
    )
    max_pv_power_with_optimizers_ambiguous: bool = Field(
        default=False,
        description="True when the datasheet does not say which models the optimizer power covers",
    )
    rated_ac_power_w: PositiveFloat
    max_apparent_power_va: PositiveFloat
    max_ac_output_current_a: PositiveFloat = Field(description="Sizes the AC OCPD and conductors")
    max_battery_discharge_w: PositiveFloat | None = None
    max_efficiency_pct: Percent
    euro_efficiency_pct: Percent | None = None

    @model_validator(mode="after")
    def _plausible(self) -> InverterVariant:
        who = f"variant {self.component_id}"
        problems: list[str] = []
        if self.rated_ac_power_w > self.max_apparent_power_va:
            problems.append(
                f"{who}: rated_ac_power_w ({self.rated_ac_power_w:g}) exceeds "
                f"max_apparent_power_va ({self.max_apparent_power_va:g})"
            )
        if self.recommended_max_pv_power_wp < self.rated_ac_power_w:
            problems.append(
                f"{who}: recommended_max_pv_power_wp ({self.recommended_max_pv_power_wp:g}) is "
                f"below rated_ac_power_w ({self.rated_ac_power_w:g})"
            )
        optimizers = self.max_pv_power_with_optimizers_wp
        if optimizers is not None and optimizers < self.recommended_max_pv_power_wp:
            problems.append(
                f"{who}: max_pv_power_with_optimizers_wp ({optimizers:g}) is below "
                f"recommended_max_pv_power_wp ({self.recommended_max_pv_power_wp:g})"
            )
        if optimizers is None and self.max_pv_power_with_optimizers_ambiguous:
            problems.append(
                f"{who}: max_pv_power_with_optimizers_ambiguous is set but "
                "max_pv_power_with_optimizers_wp is not"
            )
        if self.euro_efficiency_pct and self.euro_efficiency_pct > self.max_efficiency_pct:
            problems.append(
                f"{who}: euro_efficiency_pct ({self.euro_efficiency_pct:g}) exceeds "
                f"max_efficiency_pct ({self.max_efficiency_pct:g})"
            )
        raise_problems(problems)
        return self

    def pv_power_limit_w(self, optimizers_on_all_modules: bool) -> float:
        """Maximum PV array power (Wp) for STR-007.

        The optimizer-only value applies only when the design declares optimizers on every module
        and the datasheet gives one for this model; otherwise the recommended maximum is the limit.
        """
        if optimizers_on_all_modules and self.max_pv_power_with_optimizers_wp is not None:
            return self.max_pv_power_with_optimizers_wp
        return self.recommended_max_pv_power_wp


class InverterSpec(Strict):
    """Values every model of the family shares (field group, not used on its own)."""

    manufacturer: str = Field(min_length=1)
    model_family: str = Field(min_length=1, description="Series name as printed on the datasheet")
    startup_voltage_v: PositiveFloat
    rated_input_voltage_v: PositiveFloat
    mppt_count: PositiveInt
    inputs_per_mppt: PositiveInt
    max_input_current_per_mppt_a: PositiveFloat = Field(
        description="Operating limit: current above it is clipped"
    )
    max_short_circuit_current_per_mppt_a: PositiveFloat = Field(
        description="Hard limit for the array Isc (including bifacial gain)"
    )
    mppt_efficiency_pct: Percent | None = None
    grid: Grid
    rated_ac_voltage_v: list[PositiveFloat] = Field(min_length=1)
    frequency_hz: list[PositiveFloat] = Field(min_length=1)
    power_factor_range: PowerFactorRange
    thd_max_pct: PositiveFloat | None = None
    battery: BatteryPort | None = None
    protection: InverterProtection | None = None
    topology: str | None = None
    night_power_w: PositiveFloat | None = None
    dc_connector: str | None = None
    operating_temp_c: AscendingRange | None = None
    altitude_m: PositiveFloat | None = None
    ip_rating: str | None = None
    weight_kg: PositiveFloat | None = None
    dimensions_mm: tuple[PositiveFloat, PositiveFloat, PositiveFloat] | None = None
    certifications_safety: list[str]
    certifications_grid: list[str]

    @model_validator(mode="after")
    def _plausible_currents(self) -> InverterSpec:
        if self.max_input_current_per_mppt_a > self.max_short_circuit_current_per_mppt_a:
            raise ValueError(
                f"max_input_current_per_mppt_a ({self.max_input_current_per_mppt_a:g}) exceeds "
                f"max_short_circuit_current_per_mppt_a "
                f"({self.max_short_circuit_current_per_mppt_a:g})"
            )
        return self

    def has_certification(self, name: str) -> bool:
        """True when a safety or grid certification matches ``name`` (``"UL 1741"``).

        Case and spacing are ignored and a suffix after a separator is tolerated: ``"UL 1741"``
        matches ``"UL 1741-SB"`` but ``"IEC 617"`` does not match ``"IEC 61727"``. The Mexican
        interconnection rules use it to ask for UL 1741 / IEEE 1547 evidence.
        """
        return has_certification(name, [*self.certifications_safety, *self.certifications_grid])


def _voltage_problems(
    who: str, spec: InverterSpec, max_input_voltage_v: float, window: Range
) -> list[str]:
    low, high = window
    problems: list[str] = []
    if high > max_input_voltage_v:
        problems.append(
            f"{who}: mppt_voltage_range_v upper limit ({high:g}) exceeds max_input_voltage_v "
            f"({max_input_voltage_v:g})"
        )
    if spec.startup_voltage_v > high:
        problems.append(
            f"{who}: startup_voltage_v ({spec.startup_voltage_v:g}) is above the MPPT window "
            f"upper limit ({high:g})"
        )
    if not low <= spec.rated_input_voltage_v <= high:
        problems.append(
            f"{who}: rated_input_voltage_v ({spec.rated_input_voltage_v:g}) is outside "
            f"mppt_voltage_range_v ({low:g}, {high:g})"
        )
    return problems


class InverterFamily(InverterSpec):
    """A datasheet family of inverters: shared values once, one variant per model."""

    component_type: Literal["string_inverter", "hybrid_inverter"]
    family_id: ComponentId
    max_input_voltage_v: PositiveFloat | None = Field(
        default=None, description="Omit it when the voltage differs by model (set it per variant)"
    )
    mppt_voltage_range_v: AscendingRange | None = Field(
        default=None, description="Omit it when the window differs by model (set it per variant)"
    )
    variants: list[InverterVariant] = Field(min_length=1)
    source: Provenance

    def _resolve(self, variant: InverterVariant, problems: list[str]) -> tuple[float, Range] | None:
        """The variant's input limits (variant value or family value), or ``None`` + problems."""
        voltage = self._one_level("max_input_voltage_v", variant, problems)
        window = self._one_level("mppt_voltage_range_v", variant, problems)
        if not isinstance(voltage, float) or not isinstance(window, tuple):
            return None
        return voltage, window

    def _one_level(
        self, name: str, variant: InverterVariant, problems: list[str]
    ) -> float | Range | None:
        who = f"variant {variant.component_id}"
        at_family: float | Range | None = getattr(self, name)
        at_variant: float | Range | None = getattr(variant, name)
        if at_family is not None and at_variant is not None:
            problems.append(
                f"{who}: {name} is defined on the family and on the variant; "
                "define it at exactly one level"
            )
            return None
        if at_family is None and at_variant is None:
            problems.append(f"{who}: {name} is not defined; set it on the family or on the variant")
            return None
        return at_variant if at_variant is not None else at_family

    @model_validator(mode="after")
    def _plausible_variants(self) -> InverterFamily:
        problems = [
            f"duplicate variant component_id {name!r}"
            for name in duplicates([v.component_id for v in self.variants])
        ]
        if self.component_type == "hybrid_inverter" and self.battery is None:
            problems.append("a hybrid_inverter needs a battery port (battery is missing)")
        if self.component_type == "string_inverter" and self.battery is not None:
            problems.append("a string_inverter cannot have a battery port; use hybrid_inverter")
        phases = math.sqrt(3) if self.grid == "three_phase" else 1.0
        for variant in self.variants:
            who = f"variant {variant.component_id}"
            limits = self._resolve(variant, problems)
            if limits is not None:
                problems += _voltage_problems(who, self, *limits)
            best = min(
                abs(
                    volts * variant.max_ac_output_current_a * phases - variant.max_apparent_power_va
                )
                / variant.max_apparent_power_va
                for volts in self.rated_ac_voltage_v
            )
            if best > AC_CURRENT_TOLERANCE:
                problems.append(
                    f"{who}: max_ac_output_current_a ({variant.max_ac_output_current_a:g}) does "
                    f"not match max_apparent_power_va ({variant.max_apparent_power_va:g}) at any "
                    f"rated_ac_voltage_v {self.rated_ac_voltage_v} within "
                    f"{AC_CURRENT_TOLERANCE:.0%}"
                )
            if self.battery is None and variant.max_battery_discharge_w is not None:
                problems.append(f"{who}: max_battery_discharge_w is set but there is no battery")
        raise_problems(problems)
        return self

    def expand(self) -> list[Inverter]:
        """One standalone ``Inverter`` per variant (family values, variant values on top)."""
        shared = {name: getattr(self, name) for name in InverterSpec.model_fields}
        expanded = []
        for variant in self.variants:
            values = {name: getattr(variant, name) for name in InverterVariant.model_fields}
            for name in ("max_input_voltage_v", "mppt_voltage_range_v"):
                if values[name] is None:
                    values[name] = getattr(self, name)  # the validator guarantees one level
            expanded.append(
                Inverter(
                    component_type=self.component_type,
                    family_id=self.family_id,
                    source=self.source,
                    **shared,
                    **values,
                )
            )
        return expanded


class Inverter(InverterSpec, InverterVariant):
    """A single inverter model as the sizing engine sees it (no family/variant split)."""

    component_type: Literal["string_inverter", "hybrid_inverter"]
    family_id: ComponentId
    max_input_voltage_v: PositiveFloat  # resolved: never None here
    mppt_voltage_range_v: AscendingRange  # resolved: never None here
    source: Provenance

    @model_validator(mode="after")
    def _plausible_window(self) -> Inverter:
        raise_problems(
            _voltage_problems(
                f"{self.component_id}", self, self.max_input_voltage_v, self.mppt_voltage_range_v
            )
        )
        return self

    @property
    def reviewed(self) -> bool:
        """True once the owner has approved the record this inverter came from."""
        return self.source.reviewed
