"""Shared helpers of the Stage 3.4 sizing tests: fixture catalogue, template, request builder."""

from __future__ import annotations

import functools
from pathlib import Path
from typing import Any

from pvsld.catalogue import ComponentRegistry
from pvsld.core.policy import DEFAULT_DC_AC_POLICY, DcAcPolicy
from pvsld.core.validation import ValidationReport, validate_pv_design
from pvsld.sizing import SizingRequest, SizingResult, size_pv_system
from s1_helpers import load_example

FIXTURE_RECORDS = Path(__file__).resolve().parent / "fixtures" / "sizing" / "records"

# Components of the fixture catalogue (copies of the owner's datasheet records + the sample pair).
SAMPLE_MODULE = "XM-550"
SAMPLE_INVERTER = "YI-6000"
JINKO_650 = "JINKO-JKM650N-66HL4M-BDV"
ET_550 = "ETSOLAR-ET-M672BH550"
HUAWEI_5K = "HUAWEI-SUN2000-5KTL-L1"
HUAWEI_6K = "HUAWEI-SUN2000-6KTL-L1"
GROWATT_5K = "GROWATT-MIN-5000TL-X2"
SCHNEIDER_20A = "SCHNEIDER-A9N61652"


@functools.cache
def registry() -> ComponentRegistry:
    """The fixture catalogue (loaded once; the registry is read-only)."""
    return ComponentRegistry.load(FIXTURE_RECORDS)


def template() -> dict[str, Any]:
    """A fresh copy of the sample specification, used as the non-sizing template."""
    return load_example()


def make_request(module: str, inverters: list[str] | str = "auto", **fields: Any) -> SizingRequest:
    """A request on the sample template (Zapopan, T_min -3 C, 220 V 2F-3H service)."""
    return SizingRequest(
        template=fields.pop("template", None) or template(),
        module=module,
        inverters=inverters,  # type: ignore[arg-type]
        **fields,
    )


def size(module: str, inverters: list[str] | str = "auto", **fields: Any) -> SizingResult:
    return size_pv_system(make_request(module, inverters, **fields), registry())


def validate_selected(
    result: SizingResult, policy: DcAcPolicy = DEFAULT_DC_AC_POLICY
) -> ValidationReport:
    """Validate the selected specification with the public entry point, not the engine's gate."""
    assert result.spec is not None, "no candidate was selected"
    return validate_pv_design(result.spec, dc_ac_policy=policy)
