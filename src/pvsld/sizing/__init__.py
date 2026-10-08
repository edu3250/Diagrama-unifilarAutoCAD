"""Parametric sizing engine v1 (Stage 3.4): strings, inverter match, OCPD and conductors.

Deterministic Python on top of the component catalogue (:mod:`pvsld.catalogue`) and the rule pack
(:mod:`pvsld.core.rules`); no LLM. Given a module, one or more inverters, a site and a target, it
enumerates string configurations, rejects the ones that break a rule (naming the rule and the
numbers), ranks the rest, sizes the balance of system and returns a full parameter specification
that ``validate_pv_design`` accepts with 0 errors.

Example::

    registry = ComponentRegistry.load("datasheets/records", include_unreviewed=True)
    request = SizingRequest(
        template=load_spec_file(Path("examples/residential_7p7kwp.yaml")),
        module="JINKO-JKM650N-66HL4M-BDV",
        inverters=["GROWATT-MIN-5000TL-X2"],
        target_dc_power_w=6500,
    )
    result = size_pv_system(request, registry)
    result.selected.config.label  # "2×5"
    result.spec  # the parameter specification, ready for validate_pv_design
"""

from pvsld.sizing.engine import OBJECTIVE, size_pv_system
from pvsld.sizing.io import load_request, request_from_mapping
from pvsld.sizing.models import (
    BosSpec,
    Candidate,
    ConductorChoice,
    DcOcpdChoice,
    Issue,
    Rejection,
    Routing,
    SizingInputError,
    SizingRequest,
    SizingResult,
    StringConfig,
    StringMetrics,
)
from pvsld.sizing.report import format_report

__all__ = [
    "OBJECTIVE",
    "BosSpec",
    "Candidate",
    "ConductorChoice",
    "DcOcpdChoice",
    "Issue",
    "Rejection",
    "Routing",
    "SizingInputError",
    "SizingRequest",
    "SizingResult",
    "StringConfig",
    "StringMetrics",
    "format_report",
    "load_request",
    "request_from_mapping",
    "size_pv_system",
]
