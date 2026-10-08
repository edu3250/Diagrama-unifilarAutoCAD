"""Entry point of the validation pipeline: parse, derive, run the rule pack, report.

``validate_pv_design`` is the function behind the MCP tool of the same name (ADR-0001). It never
raises on bad input: schema problems become ``GEN-001`` findings so the caller (Claude) gets one
uniform list of things to fix.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

from pydantic import ValidationError

from pvsld.core import calc
from pvsld.core.calc import Derived
from pvsld.core.model import RULEPACK_ID, SCHEMA_VERSION, PvSystemSpec, parse_spec
from pvsld.core.policy import DEFAULT_DC_AC_POLICY, DcAcPolicy
from pvsld.core.rules import Cite, Finding, Severity, run_rules

GEN_001_MX_IDS = ("MX-A06", "MX-A08", "MX-C01", "MX-D01")
GEN_001_CITES = (Cite("PV SLD Validation Rules", "GEN-001"),)


@dataclass(frozen=True)
class ValidationReport:
    """Result of validating one specification.

    ``ok`` is ``True`` when no finding has severity ``E``. ``derived`` is ``None`` when the spec
    does not even parse. ``spec`` holds the parsed model for callers that go on to build a drawing.
    """

    ok: bool
    rulepack: str
    schema_version: str
    findings: tuple[Finding, ...]
    derived: Derived | None
    spec: PvSystemSpec | None = None

    @property
    def errors(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.WARNING)

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON types, safe to return from an MCP tool."""
        return {
            "ok": self.ok,
            "rulepack": self.rulepack,
            "schema_version": self.schema_version,
            "findings": [f.to_dict() for f in self.findings],
            "derived": asdict(self.derived) if self.derived is not None else None,
        }


def _schema_findings(error: ValidationError) -> tuple[Finding, ...]:
    findings = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"]) or "(raíz)"
        findings.append(
            Finding(
                rule_id="GEN-001",
                severity=Severity.ERROR,
                message_es=f"Entrada no válida en «{location}»: {item['msg']}.",
                mx_ids=GEN_001_MX_IDS,
                subject=location,
                cites=GEN_001_CITES,
            )
        )
    return tuple(findings)


def validate_pv_design(
    data: Mapping[str, Any] | PvSystemSpec,
    *,
    dc_ac_policy: DcAcPolicy = DEFAULT_DC_AC_POLICY,
) -> ValidationReport:
    """Validate a PV design against the parameter schema and the rule pack ``mx-gd-2026.10``.

    ``dc_ac_policy`` sets the DC/AC ratio thresholds of STR-007 (project policy, see
    :mod:`pvsld.core.policy`).
    """
    if isinstance(data, PvSystemSpec):
        spec = data
    else:
        try:
            spec = parse_spec(data)
        except ValidationError as error:
            return ValidationReport(
                ok=False,
                rulepack=RULEPACK_ID,
                schema_version=SCHEMA_VERSION,
                findings=_schema_findings(error),
                derived=None,
            )
    derived = calc.derive(spec)
    findings = tuple(run_rules(spec, derived, dc_ac_policy))
    return ValidationReport(
        ok=not any(f.severity is Severity.ERROR for f in findings),
        rulepack=RULEPACK_ID,
        schema_version=SCHEMA_VERSION,
        findings=findings,
        derived=derived,
        spec=spec,
    )
