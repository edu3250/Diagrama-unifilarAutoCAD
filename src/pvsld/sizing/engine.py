"""The sizing orchestrator: enumerate, check, rank, size the BOS, build and validate the spec.

Pipeline of :func:`size_pv_system` (deterministic Python, no LLM):

1. Every catalogue inverter requested (or all) is screened against the utility service
   (single phase, rated AC voltage) -> an *inverter* rejection with rule ``GEN-004`` otherwise.
2. Every string configuration of every inverter is evaluated by :mod:`pvsld.sizing.strings`;
   any error rejects it with the rule that failed (all reasons are kept).
3. The surviving configurations are ranked (see :data:`OBJECTIVE`).
4. In rank order, the BOS is sized (:mod:`pvsld.sizing.bos`), the full specification is built and
   run through the rule pack (the gate). A candidate that the pack rejects moves to the rejected
   list with the rule that failed; the first ``max_candidates`` that pass are the result, so the
   selected specification always validates with 0 errors.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Sequence
from typing import Any

from pvsld.catalogue import ComponentRegistry, DcBreaker, UnknownComponentError
from pvsld.catalogue import Inverter as CatalogueInverter
from pvsld.catalogue import PVModule as CatalogueModule
from pvsld.core import calc
from pvsld.core.model import SCHEMA_VERSION, Standards
from pvsld.core.severity import Severity
from pvsld.core.tables import NomTables, get_tables
from pvsld.core.validation import validate_pv_design
from pvsld.sizing import adapters, bos
from pvsld.sizing.models import (
    SUPPORTED_SYSTEMS,
    BosSpec,
    Candidate,
    Issue,
    Rejection,
    SizingInputError,
    SizingRequest,
    SizingResult,
    StringConfig,
)
from pvsld.sizing.strings import EvalContext, Evaluation, enumerate_configs, evaluate_config

OBJECTIVE = (
    "Closest deliverable DC power to the target (array STC power minus the estimated current "
    "clipping); ties: fewer warnings, lower cold string voltage relative to the inverter limit, "
    "fewer strings, inverter id. With no target the largest deliverable power wins."
)
AC_BREAKER_VOLTAGE_V = 240.0
"""Rated voltage class of the inverter-output breaker (120/240 V class devices)."""
DC_SWITCH_ASSUMPTION = (
    "DCD-1 (desconectador integrado): tensión e intensidad tomadas de los límites de entrada del "
    "inversor; el catálogo no registra la capacidad del interruptor integrado."
)
ITM_ASSUMPTION = (
    "kAIC del interruptor de salida: se toma la corriente de falla disponible del servicio como "
    "mínimo requerido; elija un interruptor comercial con al menos ese valor (catálogo de CA: "
    "Etapa 3.4b)."
)
OPTIMIZER_ASSUMPTION = (
    "Optimizadores en todos los módulos: solo se usa el límite de potencia FV con optimizadores; "
    "los límites de tensión y corriente del optimizador no se modelan (STR-009 pendiente)."
)


def _lookup(registry: ComponentRegistry, component_id: str, kind: type[Any], label: str) -> Any:
    try:
        component = registry.get(component_id)
    except UnknownComponentError as error:
        raise SizingInputError(f"{label}: {error}") from error
    if not isinstance(component, kind):
        raise SizingInputError(
            f"{label}: {component_id} is a {component.component_type}, not a {kind.__name__}"
        )
    return component


# --- Screening of inverters against the service ------------------------------------------------


def _service_problem(inverter: CatalogueInverter, nominal_v: float) -> str | None:
    """Why the inverter cannot connect to a single-phase service of ``nominal_v``, if it cannot."""
    if inverter.grid != "single_phase":
        return (
            f"El inversor {inverter.component_id} es {inverter.grid}; esta versión dimensiona "
            f"servicios monofásicos (127 V fase-neutro o 220 V fase-fase)."
        )
    accepted = {*inverter.rated_ac_voltage_v}
    if inverter.max_ac_current_reference_voltage_v is not None:
        accepted.add(inverter.max_ac_current_reference_voltage_v)
    if nominal_v not in accepted:
        shown = ", ".join(f"{v:g}" for v in sorted(accepted))
        return (
            f"El inversor {inverter.component_id} opera a {shown} V; el servicio es de "
            f"{nominal_v:g} V."
        )
    return None


# --- Ranking ------------------------------------------------------------------------------------


def _target_w(request: SizingRequest, module: CatalogueModule) -> float | None:
    if request.target_dc_power_w is not None:
        return request.target_dc_power_w
    if request.module_count_max is not None:
        return request.module_count_max * module.pmax_w
    return None


def _rank_key(
    evaluation: Evaluation, inverter: CatalogueInverter, target_w: float | None
) -> tuple[float, int, float, int, str]:
    metrics = evaluation.metrics
    distance = (
        abs(metrics.deliverable_dc_w - target_w)
        if target_w is not None
        else -metrics.deliverable_dc_w
    )
    return (
        round(distance, 3),
        len(evaluation.warnings),
        round(metrics.voc_cold_string_v / inverter.max_input_voltage_v, 6),
        evaluation.config.n_strings,
        inverter.component_id,
    )


# --- BOS and specification ------------------------------------------------------------------


def _size_bos(
    *,
    request: SizingRequest,
    module: CatalogueModule,
    inverter: CatalogueInverter,
    evaluation: Evaluation,
    standards: Standards,
    tables: NomTables,
    breakers: Sequence[DcBreaker],
) -> tuple[BosSpec | None, list[Issue]]:
    metrics, config = evaluation.metrics, evaluation.config
    site, routing = request.site, request.routing
    phases = SUPPORTED_SYSTEMS[request.utility.system]
    issues: list[Issue] = []

    needed, reason = bos.string_ocpd_required(
        module, metrics.isc_design_a, metrics.strings_per_mppt
    )
    if request.dc_ocpd == "always" and not needed:
        needed = True
        reason = "Una protección por rama por decisión de diseño (dc_ocpd: always)."
    dc_ocpd = bos.select_string_breaker(
        module=module,
        isc_a=metrics.isc_design_a,
        strings_per_input=metrics.strings_per_mppt,
        voc_cold_string_v=metrics.voc_cold_string_v,
        breakers=breakers,
        required=needed,
        reason_es=reason,
    )
    if dc_ocpd.required and dc_ocpd.breaker_id is None:
        return None, [Issue("OCP-002", Severity.ERROR, dc_ocpd.reason_es, subject=config.label)]

    ac_ocpd = bos.ac_ocpd_rating_a(inverter.max_ac_output_current_a, tables)
    string_i_max = calc.ISC_SAFETY_FACTOR * metrics.isc_design_a
    vmp_stc_string = config.n_series * module.vmp_v
    dc_length = routing.dc_string_length_m
    ac_length = routing.ac_output_length_m
    ac_voltage = request.utility.nominal_voltage_v

    dc_choice, dc_issues = bos.size_conductor(
        circuit_id="C-S",
        kind="pv_source",
        i_max_a=string_i_max,
        ocpd_a=None,
        current_carrying=2 * config.n_strings,
        ambient_c=routing.dc_ambient_c if routing.dc_ambient_c is not None else site.t_amb_max_c,
        clearance_mm=routing.rooftop_clearance_mm,
        length_m=dc_length,
        drop_pct=lambda size: calc.voltage_drop_dc_pct(
            size, dc_length, module.imp_a, vmp_stc_string, tables
        ),
        drop_limit_pct=standards.vd_limits_pct.dc,
        drop_rule="VD-001",
        tables=tables,
    )
    ac_choice, ac_issues = bos.size_conductor(
        circuit_id="C-INV",
        kind="inverter_output",
        i_max_a=inverter.max_ac_output_current_a,
        ocpd_a=ac_ocpd,
        current_carrying=_ac_current_carrying(phases),
        ambient_c=routing.ac_ambient_c if routing.ac_ambient_c is not None else site.t_amb_max_c,
        clearance_mm=None,
        length_m=ac_length,
        drop_pct=lambda size: calc.voltage_drop_ac_pct(
            size, ac_length, inverter.max_ac_output_current_a, ac_voltage, phases, tables
        ),
        drop_limit_pct=standards.vd_limits_pct.ac,
        drop_rule="VD-002",
        tables=tables,
    )
    issues += dc_issues + ac_issues
    if dc_choice is None or ac_choice is None:
        return None, issues
    return (
        BosSpec(
            dc_ocpd=dc_ocpd,
            ac_ocpd_a=ac_ocpd,
            conductors=(dc_choice, ac_choice),
            todo=bos.TODO_STAGE_3_4B,
        ),
        issues,
    )


def _ac_current_carrying(phases: int) -> int:
    """Phase conductors, plus the neutral when the circuit is line-to-neutral (1 phase)."""
    return phases + (1 if phases == 1 else 0)


_KWP = re.compile(r"\d+(?:\.\d+)?(\s*kWp)")
_KWAC = re.compile(r"\d+(?:\.\d+)?(\s*kWac)")


def _restate_size(node: Any, kwp: float, kwac: float) -> Any:
    """Rewrite the system size quoted in template text (``7.70 kWp``, ``{kwp}``, ``6.00 kWac``).

    A template written for another design (the sample says "7.70 kWp") must not leak its size into
    the sized specification: every string under ``project`` and ``title_block`` is regenerated from
    the designed power.
    """
    if isinstance(node, str):
        text = node.replace("{kwp}", f"{kwp:.2f}").replace("{kwac}", f"{kwac:.2f}")
        text = _KWP.sub(lambda m: f"{kwp:.2f}{m.group(1)}", text)
        return _KWAC.sub(lambda m: f"{kwac:.2f}{m.group(1)}", text)
    if isinstance(node, dict):
        return {key: _restate_size(value, kwp, kwac) for key, value in node.items()}
    if isinstance(node, list):
        return [_restate_size(value, kwp, kwac) for value in node]
    return node


def _build_spec(
    *,
    request: SizingRequest,
    module: CatalogueModule,
    inverter: CatalogueInverter,
    evaluation: Evaluation,
    bos_spec: BosSpec,
    standards: Standards,
) -> dict[str, Any]:
    config, metrics = evaluation.config, evaluation.metrics
    routing, utility = request.routing, request.utility
    phases = SUPPORTED_SYSTEMS[utility.system]
    spec_module = adapters.to_spec_module(module)
    spec_inverter = adapters.to_spec_inverter(
        inverter,
        ac_voltage_v=utility.nominal_voltage_v,
        phases=phases,
        optimizers_on_all_modules=request.optimizers_on_all_modules,
        ocpd_max_a=bos_spec.ac_ocpd_a,
    )
    dc_conductor, ac_conductor = bos_spec.conductors
    mppt_names = adapters.mppt_ids(inverter)

    spec = copy.deepcopy(request.template)
    spec["schema_version"] = SCHEMA_VERSION
    spec["layout"] = {**spec["layout"], "template": request.layout_template}
    spec["standards"] = standards.model_dump(mode="json")
    spec["modules"] = [spec_module.model_dump(mode="json")]
    spec["inverters"] = [spec_inverter.model_dump(mode="json")]
    spec["project"] = _restate_size(
        spec["project"], metrics.p_dc_w / 1000, inverter.rated_ac_power_w / 1000
    )
    spec["title_block"] = _restate_size(
        spec["title_block"], metrics.p_dc_w / 1000, inverter.rated_ac_power_w / 1000
    )

    strings = []
    for index in range(config.n_strings):
        strings.append(
            {
                "id": f"S{index + 1}",
                "module": adapters.MODULE_ID,
                "n_series": config.n_series,
                "inverter": adapters.INVERTER_ID,
                "mppt": mppt_names[index % len(mppt_names)],
                "tilt_deg": routing.tilt_deg,
                "azimuth_deg": routing.azimuth_deg,
            }
        )
    spec["strings"] = strings

    disconnects: list[dict[str, Any]] = []
    if spec_inverter.dc_switch_integrated:
        disconnects.append(
            {
                "id": "DCD-1",
                "integrated_in": adapters.INVERTER_ID,
                "poles": 2,
                "ue_v": spec_inverter.vdc_max_v,
                "ie_a": inverter.max_input_current_per_mppt_a,
            }
        )
    dc_ocpd = bos_spec.dc_ocpd
    if dc_ocpd.breaker_id is not None and dc_ocpd.rating_a is not None:
        disconnects += [
            {
                "id": f"DCB-S{index + 1}",
                "integrated_in": None,
                "poles": dc_ocpd.poles,
                "ue_v": dc_ocpd.ue_v,
                "ie_a": dc_ocpd.rating_a,
            }
            for index in range(config.n_strings)
        ]
    dc_bos = spec.get("dc_bos") or {}
    spec["dc_bos"] = {"combiners": [], "spds": dc_bos.get("spds", []), "disconnects": disconnects}

    ac_bos = spec["ac_bos"]
    itm_id = ac_bos["point_of_connection"]["breaker"]
    existing = {o["id"]: o for o in ac_bos.get("ocpds", [])}
    itm = {
        **existing.get(itm_id, {}),
        "id": itm_id,
        "role": "I1",
        "poles": phases,
        "rating_a": bos_spec.ac_ocpd_a,
        "voltage_v": AC_BREAKER_VOLTAGE_V,
        "kaic_ka": utility.available_fault_current_ka,
        "backfed": True,
        "at": ac_bos["point_of_connection"]["panel"],
    }
    ac_bos["ocpds"] = [o for o in ac_bos.get("ocpds", []) if o["id"] != itm_id] + [itm]

    dc_ambient = (
        routing.dc_ambient_c if routing.dc_ambient_c is not None else request.site.t_amb_max_c
    )
    ac_ambient = (
        routing.ac_ambient_c if routing.ac_ambient_c is not None else request.site.t_amb_max_c
    )
    circuits: list[dict[str, Any]] = []
    for index, string in enumerate(strings):
        circuit: dict[str, Any] = {
            "id": f"C-S{index + 1}",
            "kind": "pv_source",
            "from": string["id"],
            "to": f"{adapters.INVERTER_ID}.{string['mppt']}",
            "conductors": {
                "qty": 2,
                "size": dc_conductor.size,
                "material": "Cu",
                "insulation": "PV / THW-2",
            },
            "egc": {"size": dc_conductor.size, "type": "desnudo"},
            "raceway": (
                {
                    "type": "PVC",
                    "trade_size_mm": routing.dc_raceway_trade_size_mm,
                    "rooftop_clearance_mm": routing.rooftop_clearance_mm,
                    "ccc_count": 2 * config.n_strings,
                }
                if index == 0
                else {"ref": "C-S1"}
            ),
            "length_m": routing.dc_string_length_m,
            "ambient_c": dc_ambient,
        }
        circuits.append(circuit)
    circuits.append(
        {
            "id": "C-INV",
            "kind": "inverter_output",
            "from": f"{adapters.INVERTER_ID}.ac",
            "to": itm_id,
            "conductors": {
                "qty": phases,
                "size": ac_conductor.size,
                "material": "Cu",
                "insulation": "THW-2",
            },
            "neutral": {"size": ac_conductor.size},
            "egc": {"size": ac_conductor.size, "type": "desnudo"},
            "raceway": {
                "type": "PVC",
                "trade_size_mm": routing.ac_raceway_trade_size_mm,
                "ccc_count": _ac_current_carrying(phases),
            },
            "length_m": routing.ac_output_length_m,
            "ambient_c": ac_ambient,
        }
    )
    spec["circuits"] = circuits
    return spec


# --- Orchestrator -------------------------------------------------------------------------------


def _standards(template: dict[str, Any]) -> Standards:
    declared = template.get("standards")
    if declared is None:
        return Standards(nom_edition="NOM-001-SEDE-2012", rulepack="mx-gd-2026.10")
    return Standards.model_validate(declared)


def size_pv_system(request: SizingRequest, registry: ComponentRegistry) -> SizingResult:
    """Size a PV system from the catalogue: ranked candidates, rejections and the selected spec.

    Raises:
        SizingInputError: the module or an inverter id is unknown or of the wrong type, or the
            module cannot be expressed in schema 0.1.0.
    """
    module: CatalogueModule = _lookup(registry, request.module, CatalogueModule, "module")
    try:
        spec_module = adapters.to_spec_module(module)
    except adapters.UnsupportedComponentError as error:
        raise SizingInputError(str(error)) from error
    inverter_ids = (
        [i.component_id for i in registry.inverters()]
        if request.inverters == "auto"
        else list(request.inverters)
    )
    if not inverter_ids:
        raise SizingInputError("the catalogue has no inverters to evaluate")
    inverters: list[CatalogueInverter] = [
        _lookup(registry, name, CatalogueInverter, "inverter") for name in inverter_ids
    ]
    breakers: list[DcBreaker] = (
        registry.dc_breakers()
        if request.dc_breakers == "auto"
        else [_lookup(registry, name, DcBreaker, "dc_breaker") for name in request.dc_breakers]
    )

    site = request.site
    standards = _standards(request.template)
    tables = get_tables(standards.nom_edition)
    target_w = _target_w(request, module)

    rejected: list[Rejection] = []
    feasible: list[tuple[Evaluation, CatalogueInverter]] = []
    for inverter in inverters:
        problem = _service_problem(inverter, request.utility.nominal_voltage_v)
        if problem is not None:
            rejected.append(
                Rejection(
                    StringConfig(inverter.component_id, 0, 0),
                    (Issue("GEN-004", Severity.ERROR, problem, subject=inverter.component_id),),
                    stage="inverter",
                )
            )
            continue
        ctx = EvalContext(
            module=module,
            spec_module=spec_module,
            inverter=inverter,
            site=site,
            voc_method=standards.voc_method,
            cell_temp_rise_c=request.cell_temp_rise_c,
            optimizers_on_all_modules=request.optimizers_on_all_modules,
            policy=request.dc_ac_policy,
            module_count_min=request.module_count_min,
            module_count_max=request.module_count_max,
        )
        for n_strings, n_series in enumerate_configs(ctx):
            evaluation = evaluate_config(ctx, n_strings, n_series)
            if evaluation.feasible:
                feasible.append((evaluation, inverter))
            else:
                rejected.append(
                    Rejection(evaluation.config, evaluation.issues, "strings", evaluation.metrics)
                )

    feasible.sort(key=lambda item: _rank_key(item[0], item[1], target_w))
    candidates: list[Candidate] = []
    for evaluation, inverter in feasible:
        if len(candidates) >= request.max_candidates:
            break
        bos_spec, bos_issues = _size_bos(
            request=request,
            module=module,
            inverter=inverter,
            evaluation=evaluation,
            standards=standards,
            tables=tables,
            breakers=breakers,
        )
        if bos_spec is None:
            rejected.append(
                Rejection(
                    evaluation.config,
                    (*evaluation.issues, *bos_issues),
                    "bos",
                    evaluation.metrics,
                )
            )
            continue
        spec = _build_spec(
            request=request,
            module=module,
            inverter=inverter,
            evaluation=evaluation,
            bos_spec=bos_spec,
            standards=standards,
        )
        report = validate_pv_design(spec, dc_ac_policy=request.dc_ac_policy)
        if not report.ok:
            rejected.append(
                Rejection(
                    evaluation.config,
                    (
                        *evaluation.issues,
                        *(Issue.from_finding(f) for f in report.errors),
                    ),
                    "rule_pack",
                    evaluation.metrics,
                )
            )
            continue
        candidates.append(
            Candidate(
                rank=len(candidates) + 1,
                config=evaluation.config,
                metrics=evaluation.metrics,
                issues=(*evaluation.issues, *bos_issues),
                bos=bos_spec,
                findings=report.findings,
                spec=spec,
            )
        )

    assumptions = [*adapters.ASSUMPTIONS, ITM_ASSUMPTION, DC_SWITCH_ASSUMPTION]
    if request.optimizers_on_all_modules:
        assumptions.append(OPTIMIZER_ASSUMPTION)
    return SizingResult(
        module_id=module.component_id,
        objective=OBJECTIVE,
        target_dc_power_w=target_w,
        candidates=tuple(candidates),
        rejected=tuple(rejected),
        assumptions=tuple(assumptions),
        inverters_evaluated=tuple(inverter_ids),
    )


__all__ = ["OBJECTIVE", "size_pv_system"]
