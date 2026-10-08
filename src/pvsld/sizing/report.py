"""Readable text report of a :class:`~pvsld.sizing.models.SizingResult` (the ``pvsld size`` output).

Labels are English (the CLI language); the messages of rejections and warnings are the Spanish
texts the reviewers read.
"""

from __future__ import annotations

from collections import defaultdict

from pvsld.core.severity import Severity
from pvsld.sizing.models import Candidate, Rejection, SizingResult


def _kwp(watts: float) -> str:
    return f"{watts / 1000:.2f} kWp"


def _describe(candidate: Candidate) -> str:
    m = candidate.metrics
    clipping = f", clipping {m.clipping_pct:.1f} %" if m.clipping_pct > 0 else ""
    return (
        f"{candidate.config.inverter_id} {candidate.config.label} "
        f"({candidate.config.n_modules} modules, {_kwp(m.p_dc_w)}, DC/AC {m.dc_ac_ratio:.2f}, "
        f"Voc(T_min) {m.voc_cold_string_v:.1f} V{clipping})"
    )


def _selected_section(candidate: Candidate) -> list[str]:
    m, bos = candidate.metrics, candidate.bos
    lines = [
        f"SELECTED: {_describe(candidate)}",
        f"  string: Vmp hot {m.vmp_hot_string_v:.1f} V, Vmp cold {m.vmp_cold_string_v:.1f} V, "
        f"Isc design {m.isc_design_a:.2f} A, input {m.isc_input_a:.2f} A (1.25 x Isc x "
        f"{m.strings_per_mppt} per MPPT)",
        f"  string OCPD: {bos.dc_ocpd.reason_es}",
    ]
    if bos.dc_ocpd.breaker_id:
        d = bos.dc_ocpd
        lines.append(
            f"    -> {d.breaker_id} {d.rating_a:g} A, {d.poles}P {d.ue_v:g} V, "
            f"Icu {d.icu_ka:g} kA (minimum {d.minimum_rating_a:.1f} A)"
        )
    lines.append(f"  inverter-output breaker: {bos.ac_ocpd_a:g} A (>= 1.25 x I_ac max)")
    for c in bos.conductors:
        lines.append(
            f"  {c.circuit_id}: {c.size} Cu, I_max {c.i_max_a:.1f} A"
            + (f", OCPD {c.ocpd_a:g} A" if c.ocpd_a else "")
            + f", ampacity {c.ampacity_corrected_a:.1f} A (corrected), "
            f"voltage drop {c.vd_pct:.2f} % (limit {c.vd_limit_pct:g} %), {c.length_m:g} m"
        )
    for issue in candidate.issues:
        lines.append(f"  [{issue.severity.value}] {issue.rule_id}: {issue.message_es}")
    shown = {i.rule_id for i in candidate.issues}
    for finding in candidate.findings:
        if finding.rule_id not in shown:
            lines.append(f"  [{finding.severity.value}] {finding.rule_id}: {finding.message_es}")
    warnings = sum(1 for f in candidate.findings if f.severity is Severity.WARNING)
    lines.append(f"  rule pack mx-gd-2026.10: 0 errors, {warnings} warnings")
    return lines


def _rejection_section(rejected: tuple[Rejection, ...]) -> list[str]:
    groups: dict[tuple[str, str, str], list[Rejection]] = defaultdict(list)
    for item in rejected:
        groups[(item.config.inverter_id, item.rule_id, item.stage)].append(item)
    lines = [f"REJECTED: {len(rejected)} configuration(s)"]
    for (inverter, rule, stage), items in sorted(groups.items()):
        labels = ", ".join(i.config.label for i in items if i.config.n_strings) or "whole inverter"
        first = items[0].errors[0]
        lines.append(f"  {inverter} {rule} [{stage}] {labels}")
        lines.append(f"      e.g. {first.message_es}")
    return lines


def format_report(result: SizingResult) -> str:
    """Multi-line report: selection, BOS, ranked alternatives, grouped rejections, assumptions."""
    target = (
        f"target {_kwp(result.target_dc_power_w)}"
        if result.target_dc_power_w
        else "no target (maximum power)"
    )
    lines = [
        f"SIZING: module {result.module_id}; {target}; "
        f"{len(result.inverters_evaluated)} inverter(s) evaluated",
        f"objective: {result.objective}",
    ]
    if result.selected is None:
        lines.append("NO CANDIDATE: every configuration is rejected (see below).")
    else:
        lines += _selected_section(result.selected)
        if len(result.candidates) > 1:
            lines.append("ALTERNATIVES (ranked):")
            lines += [f"  #{c.rank} {_describe(c)}" for c in result.candidates[1:]]
    if result.rejected:
        lines += _rejection_section(result.rejected)
    lines.append("ASSUMPTIONS AND TODO:")
    lines += [f"  - {text}" for text in result.assumptions]
    if result.selected is not None:
        lines += [f"  - TODO 3.4b: {text}" for text in result.selected.bos.todo]
    return "\n".join(lines)
