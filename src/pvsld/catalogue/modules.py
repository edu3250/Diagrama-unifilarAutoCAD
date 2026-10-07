"""PV module records: one family (shared datasheet values) with one variant per power level.

A bifacial datasheet publishes two tables: STC (front side only) and BNPI (bifacial nameplate
irradiance: front 1000 W/m2 plus rear 135 W/m2). The variant keeps both; the STC values drive the
string sizing and the BNPI short-circuit current is the hard limit for the inverter input.

Example::

    family = PVModuleFamily.model_validate(yaml.safe_load(text))
    module = family.expand()[0]  # a PVModule: family values + variant values in one object
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator

from pvsld.catalogue.common import (
    EFFICIENCY_TOLERANCE_PT,
    POWER_TOLERANCE,
    ComponentId,
    PositiveFloat,
    PositiveInt,
    Provenance,
    Range,
    Strict,
    check_range,
    duplicates,
    raise_problems,
)

BIFACIALITY_KEYS = frozenset({"pmax", "voc", "isc"})
MAX_COEFFICIENT_PCT_PER_C = 1.0  # |temperature coefficient| above this is almost surely a typo


class ElectricalPoint(Strict):
    """One operating condition of a module: Pmax and the four electrical values."""

    pmax_w: PositiveFloat
    vmp_v: PositiveFloat
    imp_a: PositiveFloat
    voc_v: PositiveFloat
    isc_a: PositiveFloat


def _point_problems(who: str, point: ElectricalPoint) -> list[str]:
    problems: list[str] = []
    if point.vmp_v >= point.voc_v:
        problems.append(
            f"{who}: vmp_v ({point.vmp_v:g}) must be lower than voc_v ({point.voc_v:g})"
        )
    if point.imp_a >= point.isc_a:
        problems.append(
            f"{who}: imp_a ({point.imp_a:g}) must be lower than isc_a ({point.isc_a:g})"
        )
    product = point.vmp_v * point.imp_a
    deviation = abs(product - point.pmax_w) / point.pmax_w
    if deviation > POWER_TOLERANCE:
        problems.append(
            f"{who}: vmp_v x imp_a = {product:.1f} W differs {deviation:.1%} from pmax_w "
            f"({point.pmax_w:g}); the limit is {POWER_TOLERANCE:.0%}"
        )
    return problems


class ModuleVariant(ElectricalPoint):
    """One power level of the family; all values at STC (1000 W/m2, 25 degC, AM 1.5)."""

    component_id: ComponentId
    efficiency_pct: PositiveFloat = Field(le=100)
    bnpi: ElectricalPoint | None = Field(
        default=None, description="Bifacial nameplate irradiance values (front 1000 + rear 135)"
    )
    noct: ElectricalPoint | None = Field(
        default=None, description="Values at NOCT (800 W/m2, 20 degC ambient, 1 m/s wind)"
    )

    @model_validator(mode="after")
    def _plausible(self) -> ModuleVariant:
        problems = _point_problems(f"variant {self.component_id}", self)
        if self.bnpi is not None:
            problems += _point_problems(f"variant {self.component_id} bnpi", self.bnpi)
        if self.noct is not None:
            problems += _point_problems(f"variant {self.component_id} noct", self.noct)
            if self.noct.pmax_w >= self.pmax_w:
                problems.append(
                    f"variant {self.component_id} noct: pmax_w ({self.noct.pmax_w:g}) must be "
                    f"lower than the STC pmax_w ({self.pmax_w:g})"
                )
        raise_problems(problems)
        return self


class ModuleSpec(Strict):
    """Values every power level of the family shares (field group, not used on its own)."""

    manufacturer: str = Field(min_length=1)
    model_family: str = Field(min_length=1, description="Series name as printed on the datasheet")
    cell_type: str = Field(min_length=1)
    cells: PositiveInt
    bifacial: bool
    bifaciality_pct: dict[str, PositiveFloat] | None = Field(
        default=None, description="Rear/front ratio at STC, keys pmax, voc, isc"
    )
    dimensions_mm: tuple[PositiveFloat, PositiveFloat, PositiveFloat] = Field(
        description="(length, width, thickness)"
    )
    weight_kg: PositiveFloat
    frame: str | None = None
    front_cover: str | None = None
    junction_box: str | None = None
    max_system_voltage_v: PositiveFloat = Field(description="Maximum system voltage (IEC)")
    max_series_fuse_a: PositiveFloat = Field(description="Bounds the string overcurrent device")
    operating_temp_c: Range
    noct_c: PositiveFloat | None = Field(default=None, description="Nominal operating cell temp")
    power_tolerance_pct: Range | None = Field(
        default=None, description="Positive power tolerance as (min, max) percent of Pmax"
    )
    power_tolerance_w: Range | None = Field(
        default=None, description="Positive power tolerance as (min, max) watts"
    )
    temp_coef_pmax_pct_per_c: float
    temp_coef_voc_pct_per_c: float
    temp_coef_isc_pct_per_c: float
    connector: str | None = None
    cable_mm2: PositiveFloat | None = None
    certifications: list[str]

    @field_validator("operating_temp_c", "power_tolerance_pct", "power_tolerance_w")
    @classmethod
    def _ordered(cls, value: Range | None, info: ValidationInfo) -> Range | None:
        if value is not None:
            problem = check_range(str(info.field_name), value, allow_equal=True)
            if problem:
                raise ValueError(problem)
        return value

    @model_validator(mode="after")
    def _plausible_family_values(self) -> ModuleSpec:
        problems: list[str] = []
        for name, must_be_positive in (
            ("temp_coef_pmax_pct_per_c", False),
            ("temp_coef_voc_pct_per_c", False),
            ("temp_coef_isc_pct_per_c", True),
        ):
            value = getattr(self, name)
            if value == 0 or (value > 0) != must_be_positive:
                sign = "positive" if must_be_positive else "negative"
                problems.append(f"{name} ({value:g} %/degC) must be {sign}")
            elif abs(value) > MAX_COEFFICIENT_PCT_PER_C:
                problems.append(
                    f"{name} ({value:g} %/degC) is implausible; the datasheet unit is %/degC"
                )
        if self.bifacial and self.bifaciality_pct is None:
            problems.append("bifaciality_pct is required when bifacial is true")
        if not self.bifacial and self.bifaciality_pct is not None:
            problems.append("bifaciality_pct must be omitted when bifacial is false")
        if self.bifaciality_pct is not None:
            unknown = sorted(set(self.bifaciality_pct) - BIFACIALITY_KEYS)
            if unknown:
                problems.append(f"bifaciality_pct has unknown keys {unknown}; use pmax, voc, isc")
            problems += [
                f"bifaciality_pct.{key} ({value:g}) must be at most 100"
                for key, value in self.bifaciality_pct.items()
                if value > 100
            ]
        raise_problems(problems)
        return self

    @property
    def area_m2(self) -> float:
        """Front-face area from length x width."""
        return self.dimensions_mm[0] * self.dimensions_mm[1] / 1e6


class PVModuleFamily(ModuleSpec):
    """A datasheet family of PV modules: shared values once, one variant per power level."""

    component_type: Literal["pv_module"]
    family_id: ComponentId
    variants: list[ModuleVariant] = Field(min_length=1)
    source: Provenance

    @model_validator(mode="after")
    def _plausible_variants(self) -> PVModuleFamily:
        problems = [
            f"duplicate variant component_id {name!r}"
            for name in duplicates([v.component_id for v in self.variants])
        ]
        for variant in self.variants:
            who = f"variant {variant.component_id}"
            if variant.bnpi is not None and not self.bifacial:
                problems.append(f"{who}: bnpi is only valid for a bifacial module")
            if variant.noct is not None and self.noct_c is None:
                problems.append(f"{who}: noct values need the family value noct_c")
            computed = variant.pmax_w / (self.area_m2 * 1000) * 100
            if abs(computed - variant.efficiency_pct) > EFFICIENCY_TOLERANCE_PT:
                problems.append(
                    f"{who}: efficiency_pct ({variant.efficiency_pct:g}) differs from pmax_w / "
                    f"area = {computed:.2f} % by more than {EFFICIENCY_TOLERANCE_PT} points "
                    f"(area {self.area_m2:.3f} m2 from dimensions_mm)"
                )
            if variant.voc_v > self.max_system_voltage_v:
                problems.append(
                    f"{who}: voc_v ({variant.voc_v:g}) exceeds max_system_voltage_v "
                    f"({self.max_system_voltage_v:g})"
                )
            if variant.isc_a > self.max_series_fuse_a:
                problems.append(
                    f"{who}: isc_a ({variant.isc_a:g}) exceeds max_series_fuse_a "
                    f"({self.max_series_fuse_a:g})"
                )
        raise_problems(problems)
        return self

    def expand(self) -> list[PVModule]:
        """One standalone ``PVModule`` per variant (family values + variant values)."""
        shared = {name: getattr(self, name) for name in ModuleSpec.model_fields}
        return [
            PVModule(
                component_type=self.component_type,
                family_id=self.family_id,
                source=self.source,
                **shared,
                **{name: getattr(variant, name) for name in ModuleVariant.model_fields},
            )
            for variant in self.variants
        ]


class PVModule(ModuleSpec, ModuleVariant):
    """A single PV module model as the sizing engine sees it (no family/variant split)."""

    component_type: Literal["pv_module"]
    family_id: ComponentId
    source: Provenance

    @property
    def reviewed(self) -> bool:
        """True once the owner has approved the record this module came from."""
        return self.source.reviewed
