"""Layout template ``bt_string_residential_v1``: parameter model -> :class:`Diagram`.

All placement is computed here, on a fixed port grid, in sheet millimetres (ADR-0001, decision 2),
so the render backends stay thin. Flow is left to right (vault note "SLD Drafting Conventions"):

    strings S1, S2 -> inverter -> I1 breaker -> PI -> load centre -> I2 breaker -> MF meter -> grid

with the grounding electrode below the power path, the notes at the lower right of the schematic,
four ruled tables in the lower-left band, the symbol legend and the title and revision blocks in
the right band. One inverter and up to two strings, each on its own MPPT, are supported: this is
the single template of the S1 spike. A spec outside it raises :class:`LayoutError` with the reason
instead of drawing something wrong.
"""

from __future__ import annotations

import textwrap
from collections.abc import Sequence

from pvsld.core import calc, layers
from pvsld.core.calc import Derived
from pvsld.core.diagram import (
    A3,
    Connection,
    Diagram,
    LineItem,
    Point,
    PortRef,
    SymbolInstance,
    Table,
    TextItem,
    Viewport,
    rnd,
)
from pvsld.core.model import (
    NOM_EDITION,
    RULEPACK_ID,
    SCHEMA_VERSION,
    Circuit,
    Inverter,
    MainBreaker,
    Meter,
    Ocpd,
    Panel,
    PvSystemSpec,
    Raceway,
)
from pvsld.core.tables import NomTables, get_tables
from pvsld.symbols import LIBRARY_VERSION, get_symbol
from pvsld.symbols.catalogue import TITLE_BLOCK_HEIGHT_MM

TEMPLATE = "bt_string_residential_v1"
GRID_COMP_ID = "GRID-1"
GROUND_COMP_ID = "PT-1"
TITLE_BLOCK_COMP_ID = "TTLB-1"
NO_VALUE = "—"
MEXICAN_GRID_FREQUENCY_HZ = 60

# --- Sheet regions (sheet millimetres, origin bottom-left of the A3 sheet) ---------------------
INVERTER_XY = (115.0, 220.0)
STRING_X = 20.0
STRING_DY = 20.0
ITM1_X = 212.0
PI_X = 240.0
PANEL_X = 262.0
ITMP_X = 318.0
METER_X = 346.0
GRID_X = 372.0
GROUND_XY = (206.0, 172.0)
TITLE_BLOCK_XY = (225.0, 10.0)
REVISION_X = 225.0
LEGEND_X, LEGEND_Y_TOP = 225.0, 142.0
TABLES_X, TABLES_Y_TOP, TABLES_GAP = 15.0, 140.0, 5.0
NOTES_X, NOTES_Y_TOP = 290.0, 187.0
NOTES_WRAP = 66
MIN_REVISION_ROWS, MAX_REVISION_ROWS = 3, 5
CALLOUT_LINE_MM = 3.5


class LayoutError(ValueError):
    """The spec cannot be drawn by this template; the message says why."""


# --- Formatting (NOM-008: decimal point, space before the unit) -----------------------------------


def _n(value: float, decimals: int = 1) -> str:
    return f"{value:.{decimals}f}"


def _g(value: float) -> str:
    return f"{value:g}"


# --- Component builders ---------------------------------------------------------------------------


def _attributes(
    symbol_name: str, comp_id: str, values: dict[str, str]
) -> tuple[tuple[str, str], ...]:
    """Complete, ordered attribute values of a component (every tag of the symbol is filled)."""
    symbol = get_symbol(symbol_name)
    values = {
        "COMP_ID": comp_id,
        "IEC_REF": symbol.iec_ref,
        "NMX_REF": symbol.nmx_ref,
        **values,
    }
    missing = [tag for tag in symbol.tags if tag not in values]
    extra = [tag for tag in values if tag not in symbol.tags]
    if missing or extra:
        raise LayoutError(f"{comp_id}: attribute tags mismatch (missing {missing}, extra {extra})")
    return tuple((tag, values[tag]) for tag in symbol.tags)


def _instance(
    symbol_name: str,
    comp_id: str,
    x: float,
    y: float,
    values: dict[str, str],
    *,
    space: str = "model",
) -> SymbolInstance:
    return SymbolInstance(
        comp_id=comp_id,
        symbol=symbol_name,
        x=rnd(x),
        y=rnd(y),
        layer=get_symbol(symbol_name).layer,
        attributes=_attributes(symbol_name, comp_id, values),
        space="paper" if space == "paper" else "model",
    )


def _string_instances(
    spec: PvSystemSpec, derived: Derived, inverter: Inverter
) -> list[SymbolInstance]:
    modules = {m.id: m for m in spec.modules}
    out = []
    for index, (string, values) in enumerate(zip(spec.strings, derived.strings, strict=True)):
        module = modules[string.module]
        kwp = _n(values.p_stc_w / 1000, 2)
        y = INVERTER_XY[1] + (STRING_DY if index == 0 else -STRING_DY)
        out.append(
            _instance(
                "PVSLD_PV_STRING",
                string.id,
                STRING_X,
                y,
                {
                    "TAG": string.id,
                    "DESC": f"{string.n_series} × {_g(module.pmax_w)} W = {kwp} kWp",
                    "MODEL": module.model,
                    "MFR": module.manufacturer,
                    "MPPT": string.mppt,
                    "PMAX_W": _g(module.pmax_w),
                    "N_SERIES": str(string.n_series),
                    "KWP": _n(values.p_stc_w / 1000, 2),
                    "VOC_MAX_V": _n(values.voc_max_string_v),
                    "VMP_V": _n(values.vmp_stc_string_v),
                    "ISC_A": _n(module.isc_a, 2),
                    "IMP_A": _n(module.imp_a, 2),
                },
            )
        )
    return out


def _inverter_instance(inverter: Inverter) -> SymbolInstance:
    return _instance(
        "PVSLD_INV",
        inverter.id,
        *INVERTER_XY,
        {
            "TAG": inverter.id,
            "DESC": f"Inversor de red {_n(inverter.pac_w / 1000)} kW, {_g(inverter.vac_v)} V",
            "MFR": inverter.manufacturer,
            "MODEL": inverter.model,
            "PAC_W": _g(inverter.pac_w),
            "VAC_V": _g(inverter.vac_v),
            "PHASES": str(inverter.phases),
            "IAC_MAX_A": _g(inverter.iac_max_a),
            "VDC_MAX_V": _g(inverter.vdc_max_v),
            "MPPT_N": str(len(inverter.mppt)),
            "OCPD_MAX_A": _g(inverter.ocpd_max_a),
            "ISOLATION": inverter.isolation,
            "CERT": "; ".join(inverter.certifications) or NO_VALUE,
            "DC_SWITCH": "Integrado" if inverter.dc_switch_integrated else "No",
            "DC_SPD": inverter.dc_spd_integrated or "No",
        },
    )


def _breaker_instance(
    comp_id: str,
    x: float,
    *,
    role: str,
    poles: int,
    rating_a: float,
    voltage_v: float | None,
    kaic_ka: float | None,
    backfed: bool,
) -> SymbolInstance:
    voltage = _g(voltage_v) if voltage_v is not None else NO_VALUE
    desc = f"{poles}P {_g(rating_a)} A" + (f" {voltage} V" if voltage_v is not None else "")
    return _instance(
        "PVSLD_CB",
        comp_id,
        x,
        INVERTER_XY[1],
        {
            "TAG": comp_id,
            "ROLE": role,
            "DESC": desc,
            "POLES": str(poles),
            "RATING_A": _g(rating_a),
            "VOLT_V": voltage,
            "KAIC_KA": _g(kaic_ka) if kaic_ka is not None else NO_VALUE,
            "BACKFED": "SI" if backfed else "NO",
        },
    )


def _key_devices(spec: PvSystemSpec) -> tuple[Ocpd, MainBreaker, Meter, Panel]:
    """Locate I1, I2, the fiscal meter and the panel of the point of connection."""
    i1 = next((o for o in spec.ac_bos.ocpds if o.role == "I1"), None)
    i2 = next((b for b in spec.ac_bos.main_breakers if b.role == "I2"), None)
    meter = next((m for m in spec.ac_bos.meters if m.role == "MF"), None)
    panel = next(p for p in spec.ac_bos.panels if p.id == spec.ac_bos.point_of_connection.panel)
    if i1 is None:
        raise LayoutError(f"template {TEMPLATE} needs an I1 breaker; validate the spec first")
    if i2 is None:
        raise LayoutError(f"template {TEMPLATE} needs an I2 main breaker; validate the spec first")
    if meter is None:
        raise LayoutError(f"template {TEMPLATE} needs an MF meter; validate the spec first")
    return i1, i2, meter, panel


# --- Routing -----------------------------------------------------------------------------------


def _hvh(a: Point, b: Point) -> tuple[Point, ...]:
    """Horizontal, vertical, horizontal route (straight when the ends are level)."""
    if a.y == b.y:
        return (a, b)
    mid = rnd((a.x + b.x) / 2)
    return (a, Point(mid, a.y), Point(mid, b.y), b)


def _vh(a: Point, b: Point) -> tuple[Point, ...]:
    """Vertical then horizontal route."""
    if a.x == b.x or a.y == b.y:
        return (a, b)
    return (a, Point(a.x, b.y), b)


def _raceway(spec: PvSystemSpec, circuit: Circuit) -> Raceway:
    if circuit.raceway.ref is not None:
        return next(c for c in spec.circuits if c.id == circuit.raceway.ref).raceway
    return circuit.raceway


def _raceway_text(raceway: Raceway) -> str:
    if raceway.type is None:
        return NO_VALUE
    size = f" {_g(raceway.trade_size_mm)} mm" if raceway.trade_size_mm is not None else ""
    return f"{raceway.type}{size}"


def _conductor_text(circuit: Circuit) -> str:
    base = f"{circuit.conductors.qty}-{circuit.conductors.size} {circuit.conductors.material} "
    base += circuit.conductors.insulation
    if circuit.neutral is not None:
        base += f" + N {circuit.neutral.size}"
    return base


def _callout(
    spec: PvSystemSpec, circuit: Circuit, vd_pct: float | None, start: Point
) -> list[TextItem]:
    """Conductor callout above the first segment of a wire (four lines, top line first)."""
    egc = f"1-{circuit.egc.size} {circuit.egc.type} (p.t.)"
    drop = f"; ΔV {_n(vd_pct, 2)} %" if vd_pct is not None else ""
    lines = [
        circuit.id,
        _conductor_text(circuit),
        f"+ {egc}",
        f"{_raceway_text(_raceway(spec, circuit))}; {_g(circuit.length_m)} m{drop}",
    ]
    x = rnd(start.x + 5)
    return [
        TextItem(
            layers.TAGS, x, rnd(start.y + 2 + (len(lines) - 1 - i) * CALLOUT_LINE_MM), 2.5, text
        )
        for i, text in enumerate(lines)
    ]


# --- Tables -------------------------------------------------------------------------------------


def _string_table(spec: PvSystemSpec, derived: Derived) -> Table:
    t_min = spec.project.site.t_min_c
    rows = [
        (
            v.string_id,
            f"{v.inverter_id}.{v.mppt_id}",
            str(v.n_series),
            next(m.model for m in spec.modules if m.id == v.module_id),
            _n(v.voc_max_string_v),
            _n(v.vmp_stc_string_v),
            _n(v.vmp_hot_string_v),
            _n(v.isc_a, 2),
            _n(v.imp_a, 2),
            _n(v.p_stc_w / 1000, 2),
        )
        for v in derived.strings
    ]
    rows.append(
        (
            "Total",
            "",
            str(sum(v.n_series for v in derived.strings)),
            "",
            "",
            "",
            "",
            "",
            "",
            _n(derived.kwp_total, 2),
        )
    )
    return Table(
        id="TBL-STRINGS",
        layer=layers.TABLES,
        x=TABLES_X,
        y_top=TABLES_Y_TOP,
        col_widths=(12, 18, 18, 20, 22, 24, 24, 16, 16, 18),
        title=f"TABLA DE RAMAS (Voc máx a T mín = {_g(t_min)} °C)",
        header=(
            "Rama",
            "MPPT",
            "Módulos",
            "Modelo",
            "Voc máx (V)",
            "Vmp STC (V)",
            "Vmp cal. (V)",
            "Isc (A)",
            "Imp (A)",
            "P (kWp)",
        ),
        rows=tuple(rows),
    )


def _equipment_table(spec: PvSystemSpec) -> Table:
    rows = []
    for m in spec.modules:
        beta = f"; β Voc {_g(m.beta_voc_pct_c)} %/°C" if m.beta_voc_pct_c is not None else ""
        rows.append(
            (
                "Módulo",
                f"{m.manufacturer} {m.model}",
                f"{_g(m.pmax_w)} W; Voc {_n(m.voc_v, 2)} V; Isc {_n(m.isc_a, 2)} A; "
                f"Vmp {_n(m.vmp_v, 2)} V; Imp {_n(m.imp_a, 2)} A{beta}",
            )
        )
    for inv in spec.inverters:
        vmin = min(x.vmin_v for x in inv.mppt)
        vmax = max(x.vmax_v for x in inv.mppt)
        rows.append(
            (
                "Inversor",
                f"{inv.manufacturer} {inv.model}",
                f"{_n(inv.pac_w / 1000)} kW; {_g(inv.vac_v)} V; {_g(inv.iac_max_a)} A; "
                f"Vcd máx {_g(inv.vdc_max_v)} V; MPPT {_g(vmin)}-{_g(vmax)} V; "
                f"{len(inv.mppt)} MPPT",
            )
        )
    return Table(
        id="TBL-EQUIPMENT",
        layer=layers.TABLES,
        x=TABLES_X,
        y_top=0,
        col_widths=(20, 52, 133),
        title="DATOS DE EQUIPOS",
        header=("Equipo", "Fabricante y modelo", "Datos principales (STC y nominales)"),
        rows=tuple(rows),
    )


def _conductor_table(spec: PvSystemSpec, derived: Derived, tables: NomTables) -> Table:
    by_circuit = {c.circuit_id: c for c in derived.circuits}
    rows = []
    for circuit in spec.circuits:
        values = by_circuit[circuit.id]
        rows.append(
            (
                circuit.id,
                f"{circuit.from_} a {circuit.to}",
                _n(values.i_max_a) if values.i_max_a is not None else NO_VALUE,
                _conductor_text(circuit),
                _g(tables.awg_mm2[circuit.conductors.size]),
                f"{circuit.egc.size} {circuit.egc.type}",
                _raceway_text(_raceway(spec, circuit)),
                _g(circuit.length_m),
                _n(values.ampacity_corrected_a)
                if values.ampacity_corrected_a is not None
                else NO_VALUE,
                _n(values.vd_pct, 2) if values.vd_pct is not None else NO_VALUE,
            )
        )
    return Table(
        id="TBL-CONDUCTORS",
        layer=layers.TABLES,
        x=TABLES_X,
        y_top=0,
        col_widths=(15, 26, 16, 44, 12, 25, 20, 12, 18, 14),
        title="CÉDULA DE CONDUCTORES",
        header=(
            "Circuito",
            "Trayecto",
            "Imáx (A)",
            "Conductor",
            "mm²",
            "T (p.t.)",
            "Tubo",
            "L (m)",
            "Ampac. (A)",
            "ΔV (%)",
        ),
        rows=tuple(rows),
    )


_ROLE_TEXT = {
    "I1": "I1: Interruptor de la central",
    "I2": "I2: Interruptor principal del servicio",
    "other": "Interruptor termomagnético",
}


def _protection_table(spec: PvSystemSpec) -> Table:
    rows: list[tuple[str, ...]] = []
    for o in spec.ac_bos.ocpds:
        rows.append(
            (
                o.id,
                _ROLE_TEXT[o.role],
                str(o.poles),
                f"{_g(o.rating_a)} A",
                f"{_g(o.voltage_v)} V",
                f"{_g(o.kaic_ka)} kA",
                o.at or NO_VALUE,
            )
        )
    for b in spec.ac_bos.main_breakers:
        panel = next((p.id for p in spec.ac_bos.panels if p.main_ocpd == b.id), NO_VALUE)
        rows.append(
            (
                b.id,
                _ROLE_TEXT[b.role],
                str(b.poles),
                f"{_g(b.rating_a)} A",
                NO_VALUE,
                NO_VALUE,
                panel,
            )
        )
    for a in spec.ac_bos.disconnects:
        rows.append(
            (
                a.id,
                _ROLE_TEXT[a.role].replace("Interruptor", "Desconectador"),
                str(a.poles),
                f"{_g(a.rating_a)} A",
                NO_VALUE,
                NO_VALUE,
                NO_VALUE,
            )
        )
    for d in spec.dc_bos.disconnects:
        where = f"{d.integrated_in} (integrado)" if d.integrated_in else NO_VALUE
        rows.append(
            (
                d.id,
                "Desconectador de CD",
                str(d.poles),
                f"{_g(d.ie_a)} A",
                f"{_g(d.ue_v)} V",
                NO_VALUE,
                where,
            )
        )
    for side, spds in (("CD", spec.dc_bos.spds), ("CA", spec.ac_bos.spds)):
        for s in spds:
            volts = s.ucpv_v if s.ucpv_v is not None else s.uc_v
            rows.append(
                (
                    s.id,
                    f"DPS de {side} tipo {s.spd_type}",
                    NO_VALUE,
                    f"In {_g(s.in_ka)} kA",
                    f"{_g(volts)} V" if volts is not None else NO_VALUE,
                    NO_VALUE,
                    s.at,
                )
            )
    return Table(
        id="TBL-PROTECTIONS",
        layer=layers.TABLES,
        x=TABLES_X,
        y_top=0,
        col_widths=(18, 62, 14, 30, 22, 16, 32),
        title="CUADRO DE PROTECCIONES",
        header=("Equipo", "Función", "Polos", "Capacidad", "Tensión", "kAIC", "Ubicación"),
        rows=tuple(rows),
    )


def _legend_table(instances: Sequence[SymbolInstance]) -> Table:
    rows = []
    seen: set[str] = set()
    for item in instances:
        if item.symbol in seen or item.space == "paper":
            continue
        seen.add(item.symbol)
        symbol = get_symbol(item.symbol)
        rows.append((symbol.name, symbol.description_es, symbol.iec_ref))
    return Table(
        id="TBL-LEGEND",
        layer=layers.NOTES,
        x=LEGEND_X,
        y_top=LEGEND_Y_TOP,
        col_widths=(32, 100, 48),
        title="CUADRO DE SIMBOLOGÍA (IEC 60617; abreviaturas NMX-J-136-ANCE)",
        header=("Bloque", "Descripción", "Referencia"),
        rows=tuple(rows),
        row_height=4.5,
    )


def _revision_table(spec: PvSystemSpec) -> Table:
    revisions = spec.title_block.revisions
    if len(revisions) > MAX_REVISION_ROWS:
        raise LayoutError(f"template {TEMPLATE} shows at most {MAX_REVISION_ROWS} revisions")
    rows = [
        (r.rev, r.date.isoformat(), r.description, r.by, r.approved_by or NO_VALUE)
        for r in revisions
    ]
    rows += [("", "", "", "", "")] * (MIN_REVISION_ROWS - len(rows))
    height = 5.0 * (2 + len(rows))
    return Table(
        id="TBL-REVISIONS",
        layer=layers.REVISIONS,
        x=REVISION_X,
        y_top=rnd(TITLE_BLOCK_XY[1] + TITLE_BLOCK_HEIGHT_MM + height),
        col_widths=(15, 30, 100, 20, 20),
        title="REGISTRO DE REVISIONES",
        header=("REV", "FECHA", "DESCRIPCIÓN", "POR", "APROBÓ"),
        rows=tuple(rows),
        space="paper",
    )


def _stack(tables: Sequence[Table]) -> list[Table]:
    """Place tables one under the other in the lower-left band, top to bottom."""
    placed: list[Table] = []
    y_top = TABLES_Y_TOP
    for table in tables:
        placed.append(
            Table(
                id=table.id,
                layer=table.layer,
                x=table.x,
                y_top=rnd(y_top),
                col_widths=table.col_widths,
                title=table.title,
                header=table.header,
                rows=table.rows,
                row_height=table.row_height,
                text_height=table.text_height,
                space=table.space,
            )
        )
        y_top -= table.height + TABLES_GAP
    if y_top + TABLES_GAP < A3.border.y0 + 2:
        raise LayoutError("the tables do not fit in the lower-left band of the sheet")
    return placed


# --- Notes --------------------------------------------------------------------------------------


def _notes(spec: PvSystemSpec, derived: Derived) -> list[str]:
    site = spec.project.site
    method = {
        "coefficient": "con el coeficiente β Voc del fabricante",
        "table_690_7": "con la Tabla 690-7",
        "iec_default_1_2": "con el factor 1.2 de IEC 60364-7-712",
    }[spec.standards.voc_method]
    grounding = spec.grounding
    dc = "sin aterrizar (690-35)" if grounding.dc_system == "ungrounded_690_35" else "aterrizado"
    return [
        f"1. Tensión máxima calculada {method} a T mín = {_g(site.t_min_c)} °C "
        f"({site.t_min_source}); {spec.standards.nom_edition}, 690-7.",
        f"2. Vmp en caliente con celdas a {_g(derived.t_cell_max_c)} °C (T amb máx "
        f"{_g(site.t_amb_max_c)} °C + {_g(calc.DELTA_T_CELL_C)} °C); se usa γ Pmax como "
        f"aproximación de γ Vmp.",
        f"3. Sistema de CD {dc}; unión CD-CA: {grounding.dc_ac_bond_method}; resistencia de "
        f"diseño del electrodo ≤ {_g(grounding.design_resistance_ohm)} Ω.",
        "4. Unidades conforme a NOM-008-SE-2021. Diagrama sin escala.",
        f"5. Reglas {spec.standards.rulepack}. Borrador generado automáticamente: debe ser "
        f"revisado y firmado por el responsable (cédula profesional) antes de presentarse.",
    ]


def _note_items(notes: Sequence[str]) -> list[TextItem]:
    items = [TextItem(layers.NOTES, NOTES_X, NOTES_Y_TOP, 3.5, "NOTAS")]
    y = NOTES_Y_TOP - 5.0
    for note in notes:
        for number, line in enumerate(textwrap.wrap(note, NOTES_WRAP)):
            indent = "" if number == 0 else "   "
            items.append(TextItem(layers.NOTES, NOTES_X, rnd(y), 2.5, indent + line))
            y -= 3.6
        y -= 0.8
    return items


# --- Title block --------------------------------------------------------------------------------


def _title_block(spec: PvSystemSpec, derived: Derived) -> SymbolInstance:
    tb = spec.title_block
    site = spec.project.site
    address = site.address
    return _instance(
        "PVSLD_TTLB",
        TITLE_BLOCK_COMP_ID,
        *TITLE_BLOCK_XY,
        {
            "PROYECTO": spec.project.name,
            "CLIENTE": spec.project.client.name,
            "UBICACION": f"{address.street} {address.number}, {address.colonia}, "
            f"{address.municipio}, {address.estado}, C.P. {address.cp}",
            "RPU": spec.utility.rpu,
            "NUM_SERVICIO": spec.utility.service_number,
            "NUM_MEDIDOR": spec.utility.meter_number,
            "TARIFA": spec.utility.tariff,
            "TENSION_SUMINISTRO": f"{_g(spec.utility.nominal_voltage_v)} V {spec.utility.system}",
            "CAPACIDAD": f"{_n(derived.kwp_total, 2)} kWp / {_n(derived.kwac_total, 2)} kWac",
            "RESPONSABLE": tb.responsible.name,
            "CEDULA": tb.responsible.cedula_profesional,
            "UVIE": tb.uvie or "NO APLICA",
            "FECHA": tb.date.isoformat(),
            "EMPRESA": tb.responsible.company,
            "DIBUJO": tb.drawn_by,
            "REVISO": tb.checked_by,
            "APROBO": tb.approved_by or NO_VALUE,
            "NORMA": spec.standards.nom_edition,
            "TITULO": "Diagrama unifilar fotovoltaico",
            "PLANO_NO": tb.drawing_no,
            "HOJA": tb.sheet,
            "REV": tb.revision,
            "ESCALA": "SIN ESCALA",
            "TAG": TITLE_BLOCK_COMP_ID,
            "DESC": "Cuadro de datos del plano",
        },
        space="paper",
    )


# --- The template -------------------------------------------------------------------------------


def build_diagram(spec: PvSystemSpec, derived: Derived | None = None) -> Diagram:
    """Lay out ``spec`` on an A3 sheet.

    Raises:
        LayoutError: the spec is outside the template (more than one inverter or two strings, an
            unknown MPPT, no I1/I2/MF device) or does not fit on the sheet.
    """
    if spec.layout.template != TEMPLATE:
        raise LayoutError(f"unsupported layout template {spec.layout.template!r}")
    derived = derived or calc.derive(spec)
    tables_data = get_tables(spec.standards.nom_edition)

    if len(spec.inverters) != 1:
        raise LayoutError(
            f"template {TEMPLATE} draws exactly one inverter, got {len(spec.inverters)}"
        )
    inverter = spec.inverters[0]
    if len(spec.strings) > 2:
        raise LayoutError(f"template {TEMPLATE} draws at most two strings, got {len(spec.strings)}")
    allowed = {p.id for p in get_symbol("PVSLD_INV").ports if p.kind == "DC"}
    for string in spec.strings:
        if string.mppt not in allowed:
            raise LayoutError(f"string {string.id}: MPPT {string.mppt!r} has no port in the symbol")
    i1, i2, meter, panel = _key_devices(spec)

    # Components, in drawing order.
    instances: list[SymbolInstance] = [*_string_instances(spec, derived, inverter)]
    instances.append(_inverter_instance(inverter))
    instances.append(
        _breaker_instance(
            i1.id,
            ITM1_X,
            role="I1",
            poles=i1.poles,
            rating_a=i1.rating_a,
            voltage_v=i1.voltage_v,
            kaic_ka=i1.kaic_ka,
            backfed=i1.backfed,
        )
    )
    poc = spec.ac_bos.point_of_connection
    instances.append(
        _instance(
            "PVSLD_PI",
            poc.id,
            PI_X,
            INVERTER_XY[1],
            {
                "TAG": poc.id,
                "DESC": "Punto de interconexión",
                "PI_TYPE": poc.type,
                "PANEL": poc.panel,
                "BREAKER": poc.breaker,
            },
        )
    )
    instances.append(
        _instance(
            "PVSLD_PANEL",
            panel.id,
            PANEL_X,
            INVERTER_XY[1],
            {
                "TAG": panel.id,
                "DESC": panel.name,
                "SPEC": f"Barra {_g(panel.bus_a)} A; {panel.system}; {_g(panel.kaic_ka)} kA",
                "NAME": panel.name,
                "BUS_A": _g(panel.bus_a),
                "MAIN_ID": panel.main_ocpd,
                "MAIN_A": _g(i2.rating_a),
                "SYSTEM": panel.system,
                "KAIC_KA": _g(panel.kaic_ka),
            },
        )
    )
    instances.append(
        _breaker_instance(
            i2.id,
            ITMP_X,
            role="I2",
            poles=i2.poles,
            rating_a=i2.rating_a,
            voltage_v=None,
            kaic_ka=None,
            backfed=False,
        )
    )
    instances.append(
        _instance(
            "PVSLD_METER",
            meter.id,
            METER_X,
            INVERTER_XY[1],
            {
                "TAG": meter.id,
                "DESC": "Medidor bidireccional (MF)",
                "METER_TYPE": "MF",
                "BIDIRECTIONAL": "SI" if meter.bidirectional else "NO",
                "OWNER": meter.owner,
                "METER_NO": meter.meter_no,
            },
        )
    )
    utility = spec.utility
    instances.append(
        _instance(
            "PVSLD_GRID",
            GRID_COMP_ID,
            GRID_X,
            INVERTER_XY[1],
            {
                "TAG": "RED",
                "DESC": f"Red de distribución {utility.supplier}",
                "SPEC": f"{_g(utility.nominal_voltage_v)} V {utility.system} "
                f"{MEXICAN_GRID_FREQUENCY_HZ} Hz",
                "VOLT_V": _g(utility.nominal_voltage_v),
                "SYSTEM": utility.system,
                "FREQ_HZ": str(MEXICAN_GRID_FREQUENCY_HZ),
                "OWNER": utility.supplier,
                "ISC_KA": _g(utility.available_fault_current_ka),
            },
        )
    )
    electrode = spec.grounding.electrodes[0]
    instances.append(
        _instance(
            "PVSLD_GND",
            GROUND_COMP_ID,
            *GROUND_XY,
            {
                "TAG": GROUND_COMP_ID,
                "DESC": "Electrodo de puesta a tierra",
                "SPEC": f"{electrode.type.capitalize()} {_n(electrode.length_m, 2)} m; "
                f"≤ {_g(spec.grounding.design_resistance_ohm)} Ω",
                "ELECTRODE": electrode.type,
                "R_OHM": _g(spec.grounding.design_resistance_ohm),
                "GEC_SIZE": spec.grounding.gec_dc,
            },
        )
    )
    by_id = {item.comp_id: item for item in instances}

    # Conductors.
    connections: list[Connection] = []
    texts: list[TextItem] = []
    values_by_circuit = {c.circuit_id: c for c in derived.circuits}

    def connect(
        conn_id: str,
        kind: str,
        layer: str,
        start: PortRef,
        end: PortRef,
        *,
        route: str = "hvh",
        circuit: Circuit | None = None,
    ) -> None:
        a = by_id[start.comp_id].port_xy(start.port)
        b = by_id[end.comp_id].port_xy(end.port)
        points = _hvh(a, b) if route == "hvh" else _vh(a, b)
        connections.append(
            Connection(conn_id, kind, layer, start, end, points, circuit.id if circuit else None)
        )
        if circuit is not None:
            texts.extend(_callout(spec, circuit, values_by_circuit[circuit.id].vd_pct, points[0]))

    for string in spec.strings:
        circuit = next(
            (
                c
                for c in spec.circuits
                if c.kind == "pv_source" and c.from_.split(".")[0] == string.id
            ),
            None,
        )
        connect(
            circuit.id if circuit else f"DC-{string.id}",
            "pv_source",
            layers.DC_CONDUCTORS,
            PortRef(string.id, "OUT"),
            PortRef(inverter.id, string.mppt),
            circuit=circuit,
        )
    inverter_circuit = next((c for c in spec.circuits if c.kind == "inverter_output"), None)
    connect(
        inverter_circuit.id if inverter_circuit else "AC-INV",
        "inverter_output",
        layers.AC_CONDUCTORS,
        PortRef(inverter.id, "AC"),
        PortRef(i1.id, "IN"),
        circuit=inverter_circuit,
    )
    chain = [
        (PortRef(i1.id, "OUT"), PortRef(poc.id, "IN")),
        (PortRef(poc.id, "OUT"), PortRef(panel.id, "LEFT")),
        (PortRef(panel.id, "RIGHT"), PortRef(i2.id, "IN")),
        (PortRef(i2.id, "OUT"), PortRef(meter.id, "IN")),
        (PortRef(meter.id, "OUT"), PortRef(GRID_COMP_ID, "IN")),
    ]
    for index, (start, end) in enumerate(chain, start=1):
        connect(f"NET-{index:02d}", "ac_network", layers.AC_CONDUCTORS, start, end)
    connect(
        f"GND-{inverter.id}",
        "grounding",
        layers.GROUNDING,
        PortRef(inverter.id, "PE"),
        PortRef(GROUND_COMP_ID, "PE"),
        route="vh",
    )
    connect(
        f"GND-{panel.id}",
        "grounding",
        layers.GROUNDING,
        PortRef(panel.id, "PE"),
        PortRef(GROUND_COMP_ID, "PE"),
        route="vh",
    )
    texts.append(
        TextItem(layers.TAGS, 140.0, 174.0, 2.5, f"GEC CD: {spec.grounding.gec_dc} Cu desnudo")
    )
    texts.append(
        TextItem(layers.TAGS, 226.0, 174.0, 2.5, f"GEC CA: {spec.grounding.gec_ac} Cu desnudo")
    )

    # Headings.
    texts.append(TextItem(layers.TAGS, 15.0, 277.0, 5.0, "DIAGRAMA UNIFILAR FOTOVOLTAICO"))
    texts.append(TextItem(layers.ENCLOSURES, 20.0, 266.0, 2.5, "CIRCUITOS DE CD"))
    texts.append(TextItem(layers.ENCLOSURES, 168.0, 266.0, 2.5, "CIRCUITOS DE CA"))
    texts += _note_items(_notes(spec, derived))

    # Tables.
    stacked = _stack(
        [
            _string_table(spec, derived),
            _equipment_table(spec),
            _conductor_table(spec, derived, tables_data),
            _protection_table(spec),
        ]
    )
    all_tables = [*stacked, _legend_table(instances), _revision_table(spec)]

    # Sheet furniture (paper space).
    instances.append(_title_block(spec, derived))
    border = A3.border
    sheet_lines = [
        LineItem(layers.TITLE_BLOCK, border.x0, border.y0, border.x1, border.y0, "paper", 70),
        LineItem(layers.TITLE_BLOCK, border.x1, border.y0, border.x1, border.y1, "paper", 70),
        LineItem(layers.TITLE_BLOCK, border.x1, border.y1, border.x0, border.y1, "paper", 70),
        LineItem(layers.TITLE_BLOCK, border.x0, border.y1, border.x0, border.y0, "paper", 70),
    ]
    width = border.x1 - border.x0
    height = border.y1 - border.y0
    viewport = Viewport(
        center=Point(rnd(border.x0 + width / 2), rnd(border.y0 + height / 2)),
        size=(rnd(width), rnd(height)),
        view_center=Point(rnd(border.x0 + width / 2), rnd(border.y0 + height / 2)),
        view_height=rnd(height),
    )
    metadata = (
        ("PROJECT_ID", spec.project.id),
        ("SCHEMA_VERSION", SCHEMA_VERSION),
        ("RULEPACK", RULEPACK_ID),
        ("NOM_EDITION", NOM_EDITION),
        ("LAYOUT_TEMPLATE", TEMPLATE),
        ("SYMBOL_LIBRARY_VERSION", LIBRARY_VERSION),
    )
    return Diagram(
        sheet=A3,
        template=TEMPLATE,
        metadata=metadata,
        instances=tuple(instances),
        connections=tuple(connections),
        texts=tuple(texts),
        lines=tuple(sheet_lines),
        polylines=(),
        tables=tuple(all_tables),
        viewport=viewport,
    )


__all__ = ["TEMPLATE", "LayoutError", "build_diagram"]
