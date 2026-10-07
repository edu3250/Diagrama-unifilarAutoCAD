"""The canonical definition of the CFE symbol library (ADR-0005, Stage 4.2).

This module is the single source of truth that ``pvsld symbols build`` turns into
``symbols/pvsld-symbols-cfe.dxf``. Read it next to the legend sheet: each :class:`SymbolSpec`
carries its Spanish designation, the source it is drawn from and a reviewer note.

How the shapes were obtained. The symbols of CFE G0100-04 Appendix C (13) and the usage of
Appendix D (figures D1 and D2: earth, conductor-count ticks, polarity, junction dots) were redrawn
by hand as vector geometry (lines, arcs, circles, polylines, text) from high-resolution crops of
the specification. No raster image and no text of the specification is embedded; only the symbol
names are used. Dimensions are in millimetres at 1:1 and the proportions follow the CFE figures.

Conventions (ADR-0003):

* Block names ``PVSLD_<FUNCTION>``. Every entity names a layer of the house standard, never ``0``.
* The base point ``(0, 0)`` is the upstream connection or the left-middle of the symbol; vertical
  devices hang below it. Power flows left to right. Ports sit on the 2.5 mm grid.
* Visible attributes ``TAG`` and ``DESC`` (Spanish), hidden ``COMP_ID``, ``IEC_REF``, ``NMX_REF``
  and ``SOURCE_STANDARD`` (ADR-0005), then function-specific attributes with the unit in the tag.
  The attribute tags and port ids of the nine blocks of the code-defined catalogue (Phase 2) are
  kept so that Stage 4.3 can switch the generator over with minimal change; the inverter attribute
  ``CERT`` is dropped (certifications are out of scope, owner decision).
"""

from __future__ import annotations

import math
from collections.abc import Mapping

from pvsld.core import layers
from pvsld.symbols.cfe.model import (
    NMX_PENDING,
    NO_IEC_REF,
    SOURCE_CFE_C,
    SOURCE_CFE_D,
    SOURCE_OWN,
    TAG_HEIGHT_MM,
    TEXT_HEIGHT_MM,
    Arc,
    AttDef,
    Circle,
    Dot,
    Label,
    Line,
    Polyline,
    Port,
    Primitive,
    SymbolSpec,
)

_EQ_DC = layers.DC_EQUIPMENT
_EQ_AC = layers.AC_EQUIPMENT
_EQ_UT = layers.UTILITY_EQUIPMENT
_ENCL = layers.ENCLOSURES
_LABL = layers.LABELS
_DOTTED = "DOTTED"


def _r(value: float) -> float:
    """Round to 0.1 micrometre so that the file bytes do not depend on libm rounding."""
    return round(value, 4)


# --- Attribute helpers ---------------------------------------------------------------------------


def _common(
    *,
    description_es: str,
    source: str,
    iec_ref: str,
    nmx_ref: str = NMX_PENDING,
    tag_xy: tuple[float, float] = (0, 0),
    desc_xy: tuple[float, float] = (0, 0),
    visible: bool = True,
    layer: str = layers.TAGS,
) -> tuple[AttDef, ...]:
    """TAG and DESC (visible unless the symbol is an annotation) plus the hidden identity set."""
    return (
        AttDef("TAG", "Identificador", *tag_xy, height=TAG_HEIGHT_MM, visible=visible, layer=layer),
        AttDef(
            "DESC",
            "Descripción",
            *desc_xy,
            visible=visible,
            default=description_es,
            layer=layer,
        ),
        AttDef("COMP_ID", "Identificador en el modelo", 0, 0, visible=False, layer=layer),
        AttDef(
            "IEC_REF", "Referencia IEC 60617", 0, 0, visible=False, default=iec_ref, layer=layer
        ),
        AttDef(
            "NMX_REF",
            "Referencia NMX-J-136-ANCE",
            0,
            0,
            visible=False,
            default=nmx_ref,
            layer=layer,
        ),
        AttDef(
            "SOURCE_STANDARD",
            "Norma de origen del símbolo",
            0,
            0,
            visible=False,
            default=source,
            layer=layer,
        ),
    )


def _hidden(*specs: tuple[str, str]) -> tuple[AttDef, ...]:
    return tuple(AttDef(tag, prompt, 0, 0, visible=False) for tag, prompt in specs)


def _spec(
    name: str,
    description_es: str,
    source: str,
    layer: str,
    geometry: tuple[Primitive, ...],
    ports: tuple[Port, ...],
    *,
    iec_ref: str = NO_IEC_REF,
    nmx_ref: str = NMX_PENDING,
    tag_xy: tuple[float, float] = (0, 0),
    desc_xy: tuple[float, float] = (0, 0),
    visible: bool = True,
    extra: tuple[AttDef, ...] = (),
    note: str = "",
) -> SymbolSpec:
    attdefs = (
        *_common(
            description_es=description_es,
            source=source,
            iec_ref=iec_ref,
            nmx_ref=nmx_ref,
            tag_xy=tag_xy,
            desc_xy=desc_xy,
            visible=visible,
        ),
        *extra,
    )
    return SymbolSpec(
        name=name,
        description_es=description_es,
        source=source,
        iec_ref=iec_ref,
        nmx_ref=nmx_ref,
        layer=layer,
        geometry=geometry,
        attdefs=attdefs,
        ports=ports,
        note=note,
    )


# --- Geometry helpers ----------------------------------------------------------------------------


def _sine(
    cx: float, cy: float, width: float, amplitude: float, periods: float = 1.0, steps: int = 24
) -> tuple[tuple[float, float], ...]:
    """The CFE tilde: starts on the axis, rises to a crest, falls to a trough (``periods`` long)."""
    return tuple(
        (
            _r(cx - width / 2 + width * i / steps),
            _r(cy + amplitude * math.sin(2 * math.pi * periods * i / steps)),
        )
        for i in range(steps + 1)
    )


def _rect(x0: float, y0: float, x1: float, y1: float) -> tuple[tuple[float, float], ...]:
    return ((x0, y0), (x1, y0), (x1, y1), (x0, y1))


def _bump(
    chord_x: float, cy: float, half: float, sagitta: float, layer: str, *, right: bool
) -> Arc:
    """A shallow winding arc of chord ``2 * half`` that bulges to the right or the left."""
    radius = (half**2 + sagitta**2) / (2 * sagitta)
    spread = math.degrees(math.asin(half / radius))
    offset = radius - sagitta
    if right:
        return Arc(_r(chord_x - offset), cy, _r(radius), _r(-spread), _r(spread), layer)
    return Arc(_r(chord_x + offset), cy, _r(radius), _r(180 - spread), _r(180 + spread), layer)


# --- CFE G0100-04, Appendix C ---------------------------------------------------------------------

PV_MODULE = _spec(
    "PVSLD_PV_MODULE",
    "Módulo fotovoltaico",
    SOURCE_CFE_C,
    _EQ_DC,
    (
        Polyline(_rect(0, -10, 10, 10), _EQ_DC, closed=True),
        Polyline(((0, 10), (5, 2.5), (10, 10)), _EQ_DC),
    ),
    (Port("POS", 5, 10, "up", "DC"), Port("NEG", 5, -10, "down", "DC")),
    iec_ref="IEC 60617 S00908",
    tag_xy=(12.5, 5),
    desc_xy=(12.5, 0.5),
    extra=(
        AttDef("MODEL", "Modelo del módulo", 12.5, -4),
        *_hidden(
            ("MFR", "Fabricante del módulo"),
            ("PMAX_W", "Potencia del módulo (W)"),
            ("VOC_V", "Voc en STC (V)"),
            ("VMP_V", "Vmp en STC (V)"),
            ("ISC_A", "Isc del módulo (A)"),
            ("IMP_A", "Imp del módulo (A)"),
        ),
    ),
    note="Rectangle 1:2 with a V from the upper corners to 37 % of the height, as in the crop.",
)

SPD = _spec(
    "PVSLD_SPD",
    "Varistor (dispositivo de protección contra sobretensiones)",
    SOURCE_CFE_C,
    _EQ_DC,
    (
        Line(0, 0, 0, -5, _EQ_DC),
        Polyline(_rect(-2.5, -15, 2.5, -5), _EQ_DC, closed=True),
        Line(0, -15, 0, -20, _EQ_DC),
        Polyline(((-4, -15), (-4, -11.5), (4, -8.5), (4, -5)), _EQ_DC),
    ),
    (Port("L", 0, 0, "up", "DC"), Port("PE", 0, -20, "down", "PE")),
    tag_xy=(7, -6),
    desc_xy=(7, -10),
    extra=(
        AttDef("SPEC", "Datos del varistor", 7, -14),
        *_hidden(
            ("SPD_TYPE", "Tipo (1, 2, 3)"),
            ("UC_V", "Tensión máxima de operación continua (V)"),
            ("UP_KV", "Nivel de protección (kV)"),
            ("IN_KA", "Corriente nominal de descarga (kA)"),
        ),
    ),
    note=(
        "Vertical varistor: narrow rectangle with the bent diagonal stroke. The line port is "
        "DC because the block lives on the DC equipment layer; an AC SPD reuses it."
    ),
)

BREAKER = _spec(
    "PVSLD_CB",
    "Interruptor termomagnético (ITM)",
    SOURCE_CFE_C,
    _EQ_AC,
    (
        Line(0, 0, 3.5, 0, _EQ_AC),
        Arc(6, -0.4455, 3.4455, 29.5, 150.5, _EQ_AC),
        Line(8, 0, 11, 0, _EQ_AC),
        Circle(12, 0, 1, _EQ_AC),
        Line(13, 0, 15, 0, _EQ_AC),
        Polyline(((15, 0), (16.5, 1.5), (18.5, -1.5), (20, 0)), _EQ_AC),
    ),
    (Port("IN", 0, 0, "left", "AC"), Port("OUT", 20, 0, "right", "AC")),
    iec_ref="IEC 60617 S00287",
    tag_xy=(0, 9.5),
    desc_xy=(0, -6),
    extra=(
        AttDef("ROLE", "Función (I1, I2)", 0, 5.5),
        *_hidden(
            ("POLES", "Polos"),
            ("RATING_A", "Corriente nominal (A)"),
            ("VOLT_V", "Tensión (V)"),
            ("KAIC_KA", "Capacidad interruptiva (kA)"),
            ("BACKFED", "Alimentado en sentido inverso"),
        ),
    ),
    note="Magnetic hump over the open contact, winding loop and thermal zigzag, left to right.",
)

INVERTER = _spec(
    "PVSLD_INV",
    "Inversor de red de cadena",
    SOURCE_CFE_C,
    _EQ_AC,
    (
        Polyline(_rect(0, -22.5, 50, 22.5), _EQ_AC, closed=True),
        Line(0, -22.5, 50, 22.5, _EQ_AC),
        Line(5, 15, 13, 15, _EQ_AC),
        Line(5, 12, 13, 12, _EQ_AC),
        Polyline(_sine(40, -14, 8, 2), _EQ_AC),
        Label(1.5, 11.5, TEXT_HEIGHT_MM, "A"),
        Label(1.5, -14, TEXT_HEIGHT_MM, "B"),
    ),
    (
        Port("A", 0, 10, "left", "DC"),
        Port("B", 0, -10, "left", "DC", required=False),
        Port("AC", 50, 0, "right", "AC"),
        Port("PE", 25, -22.5, "down", "PE"),
    ),
    iec_ref="IEC 60617 S00896",
    tag_xy=(0, 36.5),
    desc_xy=(0, 32.5),
    extra=(
        AttDef("MFR", "Fabricante", 0, 28.5),
        AttDef("MODEL", "Modelo", 0, 24.5),
        *_hidden(
            ("PAC_W", "Potencia CA nominal (W)"),
            ("VAC_V", "Tensión CA nominal (V)"),
            ("PHASES", "Conductores energizados"),
            ("IAC_MAX_A", "Corriente CA máxima (A)"),
            ("VDC_MAX_V", "Tensión CD máxima (V)"),
            ("MPPT_N", "Número de MPPT"),
            ("OCPD_MAX_A", "Protección máxima CA (A)"),
            ("ISOLATION", "Aislamiento"),
            ("DC_SWITCH", "Desconectador CD integrado"),
            ("DC_SPD", "DPS CD integrado"),
        ),
    ),
    note=(
        "Box with the diagonal from lower left to upper right, '=' upper left, '~' lower right. "
        "Nearly square as in the crop; the former 'CD'/'CA' captions are replaced by the symbols."
    ),
)

METER = _spec(
    "PVSLD_METER",
    "Medidor de energía bidireccional",
    SOURCE_CFE_C,
    _EQ_UT,
    (
        Polyline(_rect(0, -10, 15, 10), _EQ_UT, closed=True),
        Line(0, 0, 15, 0, _EQ_UT),
        Line(3, 5, 12, 5, _EQ_UT),
        Polyline(((4.5, 6.2), (3, 5), (4.5, 3.8)), _EQ_UT),
        Polyline(((10.5, 6.2), (12, 5), (10.5, 3.8)), _EQ_UT),
        Label(4.6, -7, 3.2, "kWh"),
    ),
    (Port("IN", 0, 0, "left", "AC"), Port("OUT", 15, 0, "right", "AC")),
    iec_ref="IEC 60617 S00937",
    tag_xy=(0, 13),
    desc_xy=(0, -14),
    extra=_hidden(
        ("METER_TYPE", "Tipo (MF, MCE)"),
        ("BIDIRECTIONAL", "Bidireccional"),
        ("OWNER", "Propietario"),
        ("METER_NO", "Número de medidor"),
    ),
    note="Two-cell box: double-headed arrow above, 'kWh' below. Ports at the divider line.",
)

GRID = _spec(
    "PVSLD_GRID",
    "Red eléctrica de distribución",
    SOURCE_CFE_C,
    _EQ_UT,
    (Circle(10, 0, 10, _EQ_UT), Polyline(_sine(10, 0, 9, 4, periods=1.05), _EQ_UT)),
    (Port("IN", 0, 0, "left", "AC"),),
    tag_xy=(0, 12.5),
    desc_xy=(0, -15),
    extra=(
        AttDef("SPEC", "Tensión y sistema", 0, -19),
        *_hidden(
            ("VOLT_V", "Tensión nominal (V)"),
            ("SYSTEM", "Sistema"),
            ("FREQ_HZ", "Frecuencia (Hz)"),
            ("OWNER", "Suministrador"),
            ("ISC_KA", "Corriente de falla disponible (kA)"),
        ),
    ),
    note="Circle with a sine crest and trough. It replaces the former 'RED' box.",
)

ENCLOSURE = _spec(
    "PVSLD_ENCLOSURE",
    "Gabinete o estructura metálica",
    SOURCE_CFE_C,
    _ENCL,
    (Polyline(_rect(0, -15, 40, 15), _ENCL, closed=True),),
    (),
    tag_xy=(0, 18),
    desc_xy=(0, -19),
    extra=_hidden(("ENCL_TYPE", "Tipo de gabinete")),
    note=(
        "Dash-dot rectangle (layer E-ANNO-ENCL, linetype DASHDOT). Nominal 40 x 30 mm; scale the "
        "INSERT to enclose a part of the diagram. Ports: none, conductors cross the line."
    ),
)

DIODE = _spec(
    "PVSLD_DIODE",
    "Diodo de paso",
    SOURCE_CFE_C,
    _EQ_DC,
    (
        Line(0, 0, 0, -5, _EQ_DC),
        Line(-4, -5, 4, -5, _EQ_DC),
        Polyline(((0, -5), (-3.5, -12.5), (3.5, -12.5)), _EQ_DC, closed=True),
        Line(0, -12.5, 0, -17.5, _EQ_DC),
    ),
    (Port("K", 0, 0, "up", "DC"), Port("A", 0, -17.5, "down", "DC")),
    tag_xy=(6, -6),
    desc_xy=(6, -10),
    extra=_hidden(("RATING_A", "Corriente nominal (A)"), ("VRRM_V", "Tensión inversa (V)")),
    note="Cathode bar on top, triangle pointing up (current flows from anode to cathode).",
)


def _light_load() -> tuple[Primitive, ...]:
    rays: list[Primitive] = []
    for sign_x in (-1, 1):
        for sign_y in (-1, 1):
            c = math.cos(math.radians(45))
            rays.append(
                Line(
                    _r(5 + sign_x * 5 * c),
                    _r(sign_y * 5 * c),
                    _r(5 + sign_x * 7.5 * c),
                    _r(sign_y * 7.5 * c),
                    _EQ_AC,
                )
            )
    return (Circle(5, 0, 5, _EQ_AC), *rays)


def _receptacle_load() -> tuple[Primitive, ...]:
    c = math.cos(math.radians(45))
    chords: list[Primitive] = []
    for offset in (-1.1, 1.1):
        half = math.sqrt(25 - offset**2)
        # unit direction (c, c); unit normal (-c, c)
        mx, my = 5 - offset * c, offset * c
        chords.append(
            Line(
                _r(mx - half * c),
                _r(my - half * c),
                _r(mx + half * c),
                _r(my + half * c),
                _EQ_AC,
            )
        )
    return (Circle(5, 0, 5, _EQ_AC), *chords)


LOAD_LIGHT = _spec(
    "PVSLD_LOAD_LIGHT",
    "Cargas de iluminación",
    SOURCE_CFE_C,
    _EQ_AC,
    _light_load(),
    (Port("IN", 0, 0, "left", "AC"),),
    tag_xy=(0, 10),
    desc_xy=(0, -11),
    extra=_hidden(("LOAD_W", "Carga (W)"), ("VOLT_V", "Tensión (V)"), ("CIRCUIT", "Circuito")),
    note="Circle with four diagonal rays outside the circle.",
)

LOAD_RECEPT = _spec(
    "PVSLD_LOAD_RECEPT",
    "Carga de contactos",
    SOURCE_CFE_C,
    _EQ_AC,
    _receptacle_load(),
    (Port("IN", 0, 0, "left", "AC"),),
    tag_xy=(0, 8),
    desc_xy=(0, -9),
    extra=_hidden(("LOAD_W", "Carga (W)"), ("VOLT_V", "Tensión (V)"), ("CIRCUIT", "Circuito")),
    note="Circle crossed by a diagonal band (two parallel chords at 45 degrees).",
)

CURRENT_SENSOR = _spec(
    "PVSLD_CT",
    "Sensor de corriente",
    SOURCE_CFE_C,
    _EQ_UT,
    (
        Line(0, 0, 15, 0, _EQ_UT),
        Line(0, -10, 15, -10, _EQ_UT),
        Line(4.5, -12, 4.5, 2, _EQ_UT),
        Line(10.5, -12, 10.5, 2, _EQ_UT),
        Arc(7.5, 2, 3, 0, 180, _EQ_UT),
        Arc(7.5, -12, 3, 180, 360, _EQ_UT),
    ),
    (
        Port("IN", 0, 0, "left", "AC"),
        Port("OUT", 15, 0, "right", "AC"),
        Port("IN2", 0, -10, "left", "AC", required=False),
        Port("OUT2", 15, -10, "right", "AC", required=False),
    ),
    tag_xy=(0, 8),
    desc_xy=(0, -19),
    extra=(
        AttDef("SPEC", "Relación de transformación", 0, -23),
        *_hidden(("RATIO", "Relación (A/A)"), ("BURDEN_VA", "Carga (VA)"), ("CLASS", "Clase")),
    ),
    note=(
        "Stadium (rounded rectangle) crossed by two conductors, as in the crop. The second "
        "conductor (IN2/OUT2) is optional. Port kind is AC; D1 uses it on the DC side."
    ),
)

SWITCH = _spec(
    "PVSLD_SWITCH",
    "Interruptor manual",
    SOURCE_CFE_C,
    _EQ_AC,
    (
        Line(0, 0, 5, 0, _EQ_AC),
        Line(5, 0, 12.5, 7.5, _EQ_AC),
        Line(12.5, 0, 25, 0, _EQ_AC),
        Line(8.75, 3.75, 5, 8.75, _EQ_AC, linetype=_DOTTED),
        Line(8.75, 3.75, 8.75, -6.25, _EQ_AC, linetype=_DOTTED),
        Line(5, 8.75, 8.75, 8, _EQ_AC),
        Line(5, 8.75, 5.25, 4.75, _EQ_AC),
    ),
    (Port("IN", 0, 0, "left", "AC"), Port("OUT", 25, 0, "right", "AC")),
    tag_xy=(15, 5),
    desc_xy=(0, -10),
    extra=(
        AttDef("ROLE", "Función", 15, 9),
        *_hidden(
            ("POLES", "Polos"), ("RATING_A", "Corriente nominal (A)"), ("VOLT_V", "Tensión (V)")
        ),
    ),
    note="Open blade at 45 degrees, dotted operating line and the manual-actuation arrow.",
)

ISOLATION_TRANSFORMER = _spec(
    "PVSLD_XFMR_ISO",
    "Transformador de aislamiento",
    SOURCE_CFE_C,
    _EQ_AC,
    (
        Line(0, 0, 7.5, 0, _EQ_AC),
        Line(0, -20, 7.5, -20, _EQ_AC),
        Line(17.5, 0, 25, 0, _EQ_AC),
        Line(17.5, -20, 25, -20, _EQ_AC),
        *(_bump(7.5, cy, 2.5, 2.0, _EQ_AC, right=True) for cy in (-2.5, -7.5, -12.5, -17.5)),
        *(_bump(17.5, cy, 2.5, 2.0, _EQ_AC, right=False) for cy in (-2.5, -7.5, -12.5, -17.5)),
        Line(11.25, 0, 11.25, -20, _EQ_AC),
        Line(13.75, 0, 13.75, -20, _EQ_AC),
    ),
    (
        Port("IN", 0, 0, "left", "AC"),
        Port("OUT", 25, 0, "right", "AC"),
        Port("IN2", 0, -20, "left", "AC", required=False),
        Port("OUT2", 25, -20, "right", "AC", required=False),
    ),
    tag_xy=(0, 4),
    desc_xy=(0, -24),
    extra=(
        AttDef("SPEC", "Potencia y relación", 0, -28),
        *_hidden(
            ("KVA", "Potencia (kVA)"),
            ("VOLT_PRI_V", "Tensión primaria (V)"),
            ("VOLT_SEC_V", "Tensión secundaria (V)"),
            ("FREQ_HZ", "Frecuencia (Hz)"),
        ),
    ),
    note="Two windings of four shallow bumps facing each other, two core lines between them.",
)

# --- CFE G0100-04, Appendix D (usage in figures D1 and D2) ---------------------------------------

GROUND = _spec(
    "PVSLD_GND",
    "Electrodo de puesta a tierra",
    SOURCE_CFE_D,
    layers.GROUNDING,
    (
        Line(0, 0, 0, -5, layers.GROUNDING),
        Line(-6, -5, 6, -5, layers.GROUNDING),
        Line(-4, -7.5, 4, -7.5, layers.GROUNDING),
        Line(-2, -10, 2, -10, layers.GROUNDING),
    ),
    (Port("PE", 0, 0, "up", "PE"),),
    iec_ref="IEC 60617 S00200",
    tag_xy=(9, -6),
    desc_xy=(9, -10.5),
    extra=(
        AttDef("SPEC", "Electrodo y resistencia", 9, -14.5),
        *_hidden(
            ("ELECTRODE", "Tipo de electrodo"),
            ("R_OHM", "Resistencia de diseño (Ω)"),
            ("GEC_SIZE", "Calibre del conductor al electrodo"),
        ),
    ),
    note="Stem and three bars that shorten, as drawn under the inverter and the arrays in D1.",
)

CONDUCTOR_MARK = _spec(
    "PVSLD_COND_MARK",
    "Marca de número de conductores",
    SOURCE_CFE_D,
    _LABL,
    (Line(-2.5, -2.5, 0, 2.5, _LABL), Line(0, -2.5, 2.5, 2.5, _LABL)),
    (),
    visible=False,
    extra=(AttDef("N_COND", "Número de conductores", -1.5, 4),),
    note=(
        "Two slanted ticks '//' centred on the insertion point, laid over a conductor; "
        "N_COND is the printed count."
    ),
)

POLARITY_POSITIVE = _spec(
    "PVSLD_POL_POS",
    "Polaridad positiva (+)",
    SOURCE_CFE_D,
    _LABL,
    (Line(-1.5, 0, 1.5, 0, _LABL), Line(0, -1.5, 0, 1.5, _LABL)),
    (),
    visible=False,
    note="Plus sign centred on the insertion point, next to the DC terminal of the inverter.",
)

POLARITY_NEGATIVE = _spec(
    "PVSLD_POL_NEG",
    "Polaridad negativa (-)",
    SOURCE_CFE_D,
    _LABL,
    (Line(-1.5, 0, 1.5, 0, _LABL),),
    (),
    visible=False,
    note="Minus sign centred on the insertion point.",
)

JUNCTION = _spec(
    "PVSLD_JUNCTION",
    "Unión de conductores (punto)",
    SOURCE_CFE_D,
    layers.DC_CONDUCTORS,
    (Dot(0, 0, 1, layers.DC_CONDUCTORS),),
    (),
    visible=False,
    note="Filled dot of 2 mm where conductors are joined, centred on the insertion point.",
)

# --- Symbols the generator needs and CFE does not define -------------------------------------

PV_STRING = _spec(
    "PVSLD_PV_STRING",
    "Rama de módulos fotovoltaicos en serie",
    "CFE G0100-04 Apéndice C (módulo) y D (rama)",
    _EQ_DC,
    (
        Polyline(_rect(0, -10, 10, 10), _EQ_DC, closed=True),
        Polyline(((0, 10), (5, 2.5), (10, 10)), _EQ_DC),
        Polyline(_rect(20, -10, 30, 10), _EQ_DC, closed=True),
        Polyline(((20, 10), (25, 2.5), (30, 10)), _EQ_DC),
        Dot(12.5, 0, 0.6, _EQ_DC),
        Dot(15, 0, 0.6, _EQ_DC),
        Dot(17.5, 0, 0.6, _EQ_DC),
    ),
    (Port("OUT", 30, 0, "right", "DC"),),
    iec_ref="IEC 60617 S00908",
    tag_xy=(0, 12.5),
    desc_xy=(0, -14.5),
    extra=(
        AttDef("MODEL", "Modelo del módulo", 0, -18.5),
        *_hidden(
            ("MFR", "Fabricante del módulo"),
            ("MPPT", "Entrada MPPT del inversor"),
            ("PMAX_W", "Potencia del módulo (W)"),
            ("N_SERIES", "Módulos en serie"),
            ("KWP", "Potencia de la rama (kWp)"),
            ("VOC_MAX_V", "Voc máxima a T mín (V)"),
            ("VMP_V", "Vmp en STC de la rama (V)"),
            ("ISC_A", "Isc del módulo (A)"),
            ("IMP_A", "Imp del módulo (A)"),
        ),
    ),
    note=(
        "Built from the CFE module symbol: first and last module of the series, three dots for "
        "the modules in between. The single output port keeps its Phase 2 id and side."
    ),
)

POINT_OF_INTERCONNECTION = _spec(
    "PVSLD_PI",
    "Punto de interconexión (PI) con la red de distribución",
    SOURCE_OWN,
    _EQ_UT,
    (Circle(5, 0, 5, _EQ_UT), Circle(5, 0, 1.5, _EQ_UT)),
    (Port("IN", 0, 0, "left", "AC"), Port("OUT", 10, 0, "right", "AC")),
    tag_xy=(0, 7.5),
    desc_xy=(-20, -10.5),
    extra=_hidden(
        ("PI_TYPE", "Tipo de conexión"),
        ("PANEL", "Tablero de conexión"),
        ("BREAKER", "Interruptor de conexión"),
    ),
    note="CFE marks no interconnection point; kept from Phase 2 (ring with an inner circle).",
)

LOAD_CENTER = _spec(
    "PVSLD_PANEL",
    "Centro de carga o tablero con barra",
    SOURCE_CFE_D,
    _EQ_AC,
    (
        Polyline(_rect(0, -27.5, 45, 27.5), _ENCL, closed=True),
        Line(0, 0, 45, 0, _EQ_AC),
        Line(22.5, -15, 22.5, 22.5, layers.AC_CONDUCTORS, lineweight=70),
        Line(12.5, -22.5, 32.5, -22.5, layers.GROUNDING),
        Line(22.5, -27.5, 22.5, -22.5, layers.GROUNDING),
    ),
    (
        Port("LEFT", 0, 0, "left", "AC"),
        Port("RIGHT", 45, 0, "right", "AC"),
        Port("PE", 22.5, -27.5, "down", "PE"),
    ),
    iec_ref="IEC 60617 S00062",
    tag_xy=(0, 40),
    desc_xy=(0, 35.5),
    extra=(
        AttDef("SPEC", "Datos de la barra", 0, 31),
        *_hidden(
            ("NAME", "Nombre del tablero"),
            ("BUS_A", "Barra (A)"),
            ("MAIN_ID", "Interruptor principal"),
            ("MAIN_A", "Principal (A)"),
            ("SYSTEM", "Sistema"),
            ("KAIC_KA", "Capacidad interruptiva (kA)"),
        ),
    ),
    note=(
        "'Centro de carga' of figures D1 and D2: the CFE enclosure (dash-dot) around a bus and "
        "a ground bar. Geometry and ports are those of Phase 2."
    ),
)

# Title block (pie de plano): 185 x 60 mm, six rows of ten millimetres. Each field is
# (tag, caption, x0, x1, row from the top, value height). Same fields as the Phase 2 catalogue.
TITLE_BLOCK_WIDTH_MM = 185.0
TITLE_BLOCK_HEIGHT_MM = 60.0
TITLE_BLOCK_ROW_MM = 10.0
TITLE_BLOCK_FIELDS: tuple[tuple[str, str, float, float, int, float], ...] = (
    ("PROYECTO", "PROYECTO", 0, 185, 0, 3.5),
    ("CLIENTE", "CLIENTE", 0, 80, 1, 2.5),
    ("UBICACION", "UBICACIÓN", 80, 185, 1, 2.5),
    ("RPU", "RPU", 0, 40, 2, 2.5),
    ("NUM_SERVICIO", "NÚM. DE SERVICIO", 40, 90, 2, 2.5),
    ("NUM_MEDIDOR", "NÚM. DE MEDIDOR", 90, 135, 2, 2.5),
    ("TARIFA", "TARIFA", 135, 155, 2, 2.5),
    ("TENSION_SUMINISTRO", "TENSIÓN", 155, 185, 2, 2.5),
    ("CAPACIDAD", "CAPACIDAD", 0, 46, 3, 2.5),
    ("RESPONSABLE", "RESPONSABLE", 46, 104, 3, 2.5),
    ("CEDULA", "CÉDULA PROF.", 104, 138, 3, 2.5),
    ("UVIE", "UVIE", 138, 163, 3, 2.5),
    ("FECHA", "FECHA", 163, 185, 3, 2.5),
    ("EMPRESA", "EMPRESA", 0, 70, 4, 2.5),
    ("DIBUJO", "DIBUJÓ", 70, 92, 4, 2.5),
    ("REVISO", "REVISÓ", 92, 114, 4, 2.5),
    ("APROBO", "APROBÓ", 114, 136, 4, 2.5),
    ("NORMA", "NORMA", 136, 185, 4, 2.5),
    ("TITULO", "TÍTULO DEL PLANO", 0, 85, 5, 3.5),
    ("PLANO_NO", "PLANO NÚM.", 85, 113, 5, 3.5),
    ("HOJA", "HOJA", 113, 135, 5, 2.5),
    ("REV", "REV.", 135, 150, 5, 3.5),
    ("ESCALA", "ESCALA", 150, 185, 5, 2.5),
)


def _title_block() -> SymbolSpec:
    frame = layers.TITLE_BLOCK
    width, height, row_mm = TITLE_BLOCK_WIDTH_MM, TITLE_BLOCK_HEIGHT_MM, TITLE_BLOCK_ROW_MM
    items: list[Primitive] = [
        Polyline(((0, 0), (width, 0), (width, height), (0, height)), frame, True)
    ]
    for row in range(1, int(height / row_mm)):
        y = height - row * row_mm
        items.append(Line(0, y, width, y, frame, lineweight=25))
    dividers: set[tuple[float, int]] = set()
    for _tag, caption, x0, _x1, row, _height in TITLE_BLOCK_FIELDS:
        y_top = height - row * row_mm
        items.append(Label(x0 + 1.5, y_top - 3.8, TEXT_HEIGHT_MM, caption, frame))
        if x0 > 0 and (x0, row) not in dividers:
            dividers.add((x0, row))
            items.append(Line(x0, y_top, x0, y_top - row_mm, frame, lineweight=25))
    fields = tuple(
        AttDef(
            tag,
            caption.title(),
            x0 + 1.5,
            height - row * row_mm - 8.8,
            value_height,
            layer=frame,
        )
        for tag, caption, x0, _x1, row, value_height in TITLE_BLOCK_FIELDS
    )
    description = "Cuadro de datos del plano (pie de plano)"
    nmx_ref = "NMX-J-136-ANCE Sección 5"
    attdefs = (
        *fields,
        *_common(
            description_es=description,
            source=SOURCE_OWN,
            iec_ref=NO_IEC_REF,
            nmx_ref=nmx_ref,
            visible=False,
            layer=frame,
        ),
    )
    return SymbolSpec(
        name="PVSLD_TTLB",
        description_es=description,
        source=SOURCE_OWN,
        iec_ref=NO_IEC_REF,
        nmx_ref=nmx_ref,
        layer=frame,
        geometry=tuple(items),
        attdefs=attdefs,
        ports=(),
        note="Mexican title block with 23 attribute fields; the layout is the Phase 2 one.",
    )


TITLE_BLOCK = _title_block()

# Order of the legend: the Appendix C symbols in the order of the specification (left column, then
# right column), then what Appendix D adds, then what only the generator needs.
LIBRARY: tuple[SymbolSpec, ...] = (
    PV_MODULE,
    SPD,
    BREAKER,
    INVERTER,
    METER,
    GRID,
    ENCLOSURE,
    DIODE,
    LOAD_LIGHT,
    CURRENT_SENSOR,
    SWITCH,
    ISOLATION_TRANSFORMER,
    LOAD_RECEPT,
    GROUND,
    CONDUCTOR_MARK,
    POLARITY_POSITIVE,
    POLARITY_NEGATIVE,
    JUNCTION,
    PV_STRING,
    LOAD_CENTER,
    POINT_OF_INTERCONNECTION,
    TITLE_BLOCK,
)

SYMBOLS: Mapping[str, SymbolSpec] = {spec.name: spec for spec in LIBRARY}


def get_symbol(name: str) -> SymbolSpec:
    """Return the symbol called ``name``.

    Raises:
        KeyError: the library has no such block.
    """
    try:
        return SYMBOLS[name]
    except KeyError:
        raise KeyError(f"unknown symbol {name!r}; library has {', '.join(SYMBOLS)}") from None
