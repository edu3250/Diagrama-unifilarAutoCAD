"""Output shapes of the MCP tools and their conversion from the service layer.

The pydantic models double as the ``outputSchema`` the server advertises, so Claude (and any other
client) knows the shape of a result before calling. Every model is kept concise on purpose: the host
budgets are 25k tokens (Claude Code) and about 150k characters (Claude Desktop), and the text that
Claude reads is also what it pays for.

Findings keep the Spanish message that the reviewers read; field names and the hints around them
are English because they are written for the model.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from pvsld.core.rules import Finding, Severity
from pvsld.core.validation import ValidationReport

__all__ = [
    "MAX_FINDINGS",
    "FindingOut",
    "GenerateOutput",
    "ValidationOutput",
    "finding_lines",
    "generate_text",
    "validation_output",
    "validation_text",
]

# A spec that is garbage can yield hundreds of schema findings; the first ones are enough to fix.
MAX_FINDINGS = 50
MAX_TEXT_FINDINGS = 25

_SEVERITY_NAMES: dict[Severity, Literal["error", "warning", "info"]] = {
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.INFO: "info",
}
_SEVERITY_ORDER = {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}


class FindingOut(BaseModel):
    """One rule violation or observation."""

    rule_id: str = Field(
        description="Rule of the pack mx-gd-2026.10, for example VOLT-001; GEN-001 means the input "
        "does not fit the parameter schema."
    )
    severity: Literal["error", "warning", "info"] = Field(
        description="An error blocks drawing; a warning does not."
    )
    subject: str = Field(description="What it is about: a component id (S1), a circuit or a path.")
    message_es: str = Field(
        description="Spanish message: what is wrong, the numbers, and usually the limit to respect."
    )
    mx_ids: list[str] = Field(description="Checklist items of the Mexican submission (MX-xxx).")
    cites: list[str] = Field(
        description="Normative citations, for example NOM-001-SEDE-2012 690-7."
    )


class ValidationOutput(BaseModel):
    """Result of ``validate_pv_design`` (also embedded in the result of the generator)."""

    ok: bool = Field(description="True when no finding is an error: the design can be drawn.")
    summary: str = Field(description="One line: verdict, error and warning counts, main figures.")
    rulepack: str
    schema_version: str
    errors: int
    warnings: int
    findings: list[FindingOut] = Field(
        description=f"Errors first; at most {MAX_FINDINGS} (see findings_total)."
    )
    findings_total: int
    derived: dict[str, Any] | None = Field(
        default=None,
        description="Computed values: kWp, kWac, per-string Voc at T_min, per-circuit voltage "
        "drop and ampacity. None when the spec does not parse.",
    )
    next_step: str = Field(description="What to do next.")


class GenerateOutput(BaseModel):
    """Result of ``generate_single_line_diagram``."""

    ok: bool = Field(description="True only when the DXF was written and read back clean.")
    summary: str
    drawing_id: str | None = Field(
        default=None, description="Opaque handle of the drawing; changes when its content changes."
    )
    dxf_path: str | None = Field(default=None, description="Absolute path of the DXF R2018 file.")
    png_path: str | None = Field(
        default=None, description="Absolute path of the full-resolution PNG preview."
    )
    sha256: str | None = Field(default=None, description="SHA-256 of the DXF bytes.")
    size_bytes: int | None = None
    unchanged: bool = Field(
        default=False, description="True when a file with identical content already existed."
    )
    readback: dict[str, Any] | None = Field(
        default=None,
        description="Verification of the written file: audit, INSERT counts per block, attribute "
        "round trip by COMP_ID, dangling ports, entities on layer 0, problems.",
    )
    validation: ValidationOutput | None = Field(
        default=None,
        description="Present when generation was refused because the spec has errors.",
    )
    preview: str | None = Field(
        default=None,
        description="Size of the preview image attached to this result, or why it is missing.",
    )
    timings_ms: dict[str, float] = Field(default_factory=dict)
    next_step: str


def _round(value: Any, digits: int = 3) -> Any:
    """Round floats in nested plain data so the result is short and stable."""
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, dict):
        return {key: _round(item, digits) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_round(item, digits) for item in value]
    return value


def _finding_out(finding: Finding) -> FindingOut:
    return FindingOut(
        rule_id=finding.rule_id,
        severity=_SEVERITY_NAMES[finding.severity],
        subject=finding.subject,
        message_es=finding.message_es,
        mx_ids=list(finding.mx_ids),
        cites=[str(cite) for cite in finding.cites],
    )


def _headline(report: ValidationReport) -> str:
    verdict = "OK" if report.ok else "FAILED"
    text = f"{verdict}: {len(report.errors)} errors, {len(report.warnings)} warnings"
    text += f" against {report.rulepack}"
    if report.derived is not None:
        text += f"; {report.derived.kwp_total:.2f} kWp DC, {report.derived.kwac_total:.2f} kWac"
    return text


def validation_output(report: ValidationReport, *, with_derived: bool = True) -> ValidationOutput:
    """Convert a service report; findings are ordered errors first and capped."""
    ordered = sorted(report.findings, key=lambda finding: _SEVERITY_ORDER[finding.severity])
    if report.ok:
        next_step = "Call generate_single_line_diagram with this same spec" + (
            " (review the warnings first)." if report.warnings else "."
        )
    else:
        next_step = (
            "Fix every error in the spec (the Spanish message names the limit) and call "
            "validate_pv_design again. Do not call generate_single_line_diagram until ok is true."
        )
    derived = report.derived
    return ValidationOutput(
        ok=report.ok,
        summary=_headline(report),
        rulepack=report.rulepack,
        schema_version=report.schema_version,
        errors=len(report.errors),
        warnings=len(report.warnings),
        findings=[_finding_out(finding) for finding in ordered[:MAX_FINDINGS]],
        findings_total=len(ordered),
        derived=_round(report.to_dict()["derived"]) if with_derived and derived else None,
        next_step=next_step,
    )


def finding_lines(findings: list[FindingOut], total: int) -> list[str]:
    """Compact text lines for the findings, for hosts that show only the text content."""
    lines = [
        f"- [{item.severity}] {item.rule_id} {item.subject}: {item.message_es} "
        f"({', '.join(item.mx_ids)}; {'; '.join(item.cites)})"
        for item in findings[:MAX_TEXT_FINDINGS]
    ]
    if total > len(lines):
        lines.append(f"- ... {total - len(lines)} more finding(s); see structured content.")
    return lines


def validation_text(output: ValidationOutput) -> str:
    """Text content of the validation result: summary, findings, next step."""
    lines = [output.summary, *finding_lines(output.findings, output.findings_total)]
    lines.append(output.next_step)
    return "\n".join(lines)


def generate_text(output: GenerateOutput) -> str:
    """Text content of the generator result (the image, when any, is a separate block)."""
    lines = [output.summary]
    if output.validation is not None:
        lines += finding_lines(output.validation.findings, output.validation.findings_total)
    if output.drawing_id is not None:
        lines.append(f"drawing_id: {output.drawing_id}")
        lines.append(f"dxf: {output.dxf_path}")
        if output.png_path:
            lines.append(f"png: {output.png_path}")
        lines.append(f"sha256: {output.sha256}")
    if output.readback is not None:
        readback = output.readback
        lines.append(
            f"read-back: audit {readback['audit']['errors']} errors/{readback['audit']['fixes']} "
            f"fixes, attributes {readback['attribute_roundtrip']}, dangling ports "
            f"{len(readback['dangling_ports'])}, entities on layer 0: "
            f"{readback['entities_on_layer_0']}"
        )
        lines += [f"problem: {problem}" for problem in readback["problems"]]
    if output.preview:
        lines.append(f"preview: {output.preview}")
    lines.append(output.next_step)
    return "\n".join(lines)
