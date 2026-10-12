"""Cable records: one datasheet range, one variant per conductor size (Stage 3.4b, 2026-10-09).

The sizing engine reads the overall diameter of the chosen size to fill the raceway (NOM Chapter
10, Table 1 and note 5: conductors outside Table 5, such as PV wire, use their real dimensions).
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from pvsld.catalogue.common import (
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
from pvsld.core.model import ConductorSize


class CableVariant(Strict):
    """One conductor size of the range (one catalogue reference)."""

    component_id: ComponentId = Field(description="Catalogue reference, e.g. VIAKON-PV2000-10AWG")
    size: ConductorSize
    area_mm2: PositiveFloat = Field(description="Nominal cross-section of the copper")
    strands: PositiveInt
    conductor_diameter_mm: PositiveFloat
    insulation_mm: PositiveFloat = Field(description="Insulation thickness")
    outer_diameter_mm: PositiveFloat = Field(description="Approximate overall diameter")
    weight_kg_per_100m: PositiveFloat | None = None
    ampacity_a: tuple[float, float, float] | None = Field(
        default=None, description="Printed ampacity in the 60, 75 and 90 degC columns"
    )


class CableSpec(Strict):
    """Values every size of the range shares (field group, not used on its own)."""

    manufacturer: str = Field(min_length=1)
    range_name: str = Field(min_length=1)
    material: Literal["Cu"]
    insulation: str = Field(min_length=1, description="Insulation material and listing types")
    application: Literal["pv", "building"] = Field(
        description="pv: PV source and output circuits; building: general wiring"
    )
    rated_voltage_v: PositiveFloat
    max_conductor_temp_c: PositiveFloat
    standards: list[str] = Field(min_length=1)
    listings: list[str] | None = None
    min_temp_c: float | None = None
    temp_range_c: Range | None = None

    @model_validator(mode="after")
    def _plausible(self) -> CableSpec:
        problem = check_range("temp_range_c", self.temp_range_c) if self.temp_range_c else None
        raise_problems([problem] if problem else [])
        return self


class CableFamily(CableSpec):
    """A datasheet range of cables: shared values once, one variant per size."""

    component_type: Literal["conductor"]
    family_id: ComponentId
    variants: list[CableVariant] = Field(min_length=1)
    source: Provenance

    @model_validator(mode="after")
    def _plausible_variants(self) -> CableFamily:
        problems = [
            f"duplicate variant component_id {name!r}"
            for name in duplicates([v.component_id for v in self.variants])
        ]
        problems += [
            f"duplicate size {name} in the family"
            for name in duplicates([v.size for v in self.variants])
        ]
        problems += [
            f"variant {v.component_id}: outer diameter {v.outer_diameter_mm:g} mm is not above "
            f"the conductor diameter {v.conductor_diameter_mm:g} mm"
            for v in self.variants
            if v.outer_diameter_mm <= v.conductor_diameter_mm
        ]
        raise_problems(problems)
        return self

    def expand(self) -> list[Cable]:
        """One standalone ``Cable`` per variant (family values + variant values)."""
        shared = {name: getattr(self, name) for name in CableSpec.model_fields}
        return [
            Cable(
                component_type=self.component_type,
                family_id=self.family_id,
                source=self.source,
                **shared,
                **{name: getattr(variant, name) for name in CableVariant.model_fields},
            )
            for variant in self.variants
        ]


class Cable(CableSpec, CableVariant):
    """One cable size as the sizing engine sees it."""

    component_type: Literal["conductor"]
    family_id: ComponentId
    source: Provenance

    @property
    def reviewed(self) -> bool:
        """True once the owner has approved the record this cable came from."""
        return self.source.reviewed
