"""Symbol catalogue defined in code: block geometry, attribute tags, insertion point and ports.

This is the single source of truth of the symbol library (ADR-0001 point 6, ADR-0003). Each
:class:`SymbolDef` is a plain description; a backend turns it into whatever its CAD needs (an ezdxf
``BLOCK`` here, a ``BlockTableRecord`` in the future AutoCAD backend), so both backends insert
identical block definitions.

Conventions (ADR-0003):

* Block names ``PVSLD_<FUNCTION>``; XDATA application id ``PVSLD``.
* Every component carries the attributes ``TAG`` and ``DESC`` (visible, Spanish values) and the
  hidden ``COMP_ID`` (key into the parameter model), ``IEC_REF`` and ``NMX_REF``. Function-specific
  attributes follow the vault note "PV Electrical Symbology": uppercase ASCII tags with the unit
  in the tag (``RATING_A``, ``VOLT_V``). Spanish text lives in values, never in tags.
* The base point (0, 0) is the upstream connection or the left-middle of the symbol, and every
  port sits on the 2.5 mm grid, so alignment is arithmetic. Power flows left to right.
* Symbols are drawn at 1:1 in sheet millimetres (about 10-20 mm high on an A3 sheet).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pvsld.core import layers

LIBRARY_VERSION = "0.1.0"
APP_ID = "PVSLD"
BLOCK_PREFIX = "PVSLD_"

PortKind = Literal["DC", "AC", "PE"]
Direction = Literal["left", "right", "up", "down"]

TEXT_HEIGHT_MM = 2.5
TAG_HEIGHT_MM = 3.5
HIDDEN_ATTRIBUTES: tuple[str, ...] = ("COMP_ID", "IEC_REF", "NMX_REF")
NO_IEC_REF = "-"
"""Symbols without an IEC 60617 counterpart in the vault catalogue (PI marker, utility network)."""
NMX_PENDING = "NMX-J-136-ANCE (pendiente)"
"""Placeholder until the purchased NMX-J-136-ANCE text confirms the figure numbers."""


@dataclass(frozen=True)
class Port:
    """A connection point in block-local millimetres. Optional ports may stay unconnected."""

    id: str
    x: float
    y: float
    direction: Direction
    kind: PortKind
    required: bool = True


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    layer: str
    lineweight: int | None = None


@dataclass(frozen=True)
class Polyline:
    points: tuple[tuple[float, float], ...]
    layer: str
    closed: bool = False


@dataclass(frozen=True)
class Circle:
    cx: float
    cy: float
    radius: float
    layer: str


@dataclass(frozen=True)
class Label:
    """Fixed text that is part of the symbol (for example ``CD`` and ``CA`` in the inverter)."""

    x: float
    y: float
    height: float
    text: str
    layer: str = layers.TAGS


Primitive = Line | Polyline | Circle | Label


@dataclass(frozen=True)
class AttDef:
    """Attribute definition: ``(x, y)`` is the left baseline of the text, in block coordinates."""

    tag: str
    prompt_es: str
    x: float
    y: float
    height: float = TEXT_HEIGHT_MM
    visible: bool = True
    default: str = ""
    layer: str = layers.TAGS


@dataclass(frozen=True)
class SymbolDef:
    """One block of the library."""

    name: str
    function: str
    description_es: str
    iec_ref: str
    layer: str
    geometry: tuple[Primitive, ...]
    attdefs: tuple[AttDef, ...]
    ports: tuple[Port, ...]
    nmx_ref: str = NMX_PENDING
    library_version: str = LIBRARY_VERSION

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(a.tag for a in self.attdefs)

    def port(self, port_id: str) -> Port:
        for port in self.ports:
            if port.id == port_id:
                return port
        raise KeyError(f"symbol {self.name} has no port {port_id!r}")

    def to_dict(self) -> dict[str, object]:
        """Plain data for the ``pvsld://symbols`` resource."""
        return {
            "block": self.name,
            "function": self.function,
            "description_es": self.description_es,
            "iec_ref": self.iec_ref,
            "version": self.library_version,
            "layer": self.layer,
            "ports": [
                {
                    "id": p.id,
                    "xy": [p.x, p.y],
                    "dir": p.direction,
                    "kind": p.kind,
                    "required": p.required,
                }
                for p in self.ports
            ],
            "attributes": [
                {"tag": a.tag, "prompt": a.prompt_es, "visible": a.visible} for a in self.attdefs
            ],
        }


def _common(
    *, tag_xy: tuple[float, float], desc_xy: tuple[float, float], desc_prompt: str = "Descripción"
) -> tuple[AttDef, ...]:
    """TAG and DESC (visible) plus the hidden identity attributes shared by every component."""
    return (
        AttDef("TAG", "Identificador", *tag_xy, height=TAG_HEIGHT_MM),
        AttDef("DESC", desc_prompt, *desc_xy),
        AttDef("COMP_ID", "Identificador en el modelo", 0, 0, visible=False),
        AttDef("IEC_REF", "Referencia IEC 60617", 0, 0, visible=False),
        AttDef("NMX_REF", "Referencia NMX-J-136-ANCE", 0, 0, visible=False),
    )


def _hidden(*specs: tuple[str, str]) -> tuple[AttDef, ...]:
    return tuple(AttDef(tag, prompt, 0, 0, visible=False) for tag, prompt in specs)


_EQ_DC = layers.DC_EQUIPMENT
_EQ_AC = layers.AC_EQUIPMENT
_EQ_UT = layers.UTILITY_EQUIPMENT

PV_STRING = SymbolDef(
    name="PVSLD_PV_STRING",
    function="Rama fotovoltaica",
    description_es="Rama de módulos fotovoltaicos en serie",
    iec_ref="IEC 60617 S00908",
    layer=_EQ_DC,
    geometry=(
        Polyline(((0, -10), (30, -10), (30, 10), (0, 10)), _EQ_DC, closed=True),
        Line(0, -10, 30, 10, _EQ_DC),
        Label(21, -8.5, TEXT_HEIGHT_MM, "FV"),
    ),
    attdefs=(
        *_common(tag_xy=(0, 12.5), desc_xy=(0, -14.5)),
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
    ports=(Port("OUT", 30, 0, "right", "DC"),),
)

INVERTER = SymbolDef(
    name="PVSLD_INV",
    function="Inversor",
    description_es="Inversor de red de cadena",
    iec_ref="IEC 60617 S00896",
    layer=_EQ_AC,
    geometry=(
        Polyline(((0, -32.5), (45, -32.5), (45, 32.5), (0, 32.5)), _EQ_AC, closed=True),
        Line(0, -32.5, 45, 32.5, _EQ_AC),
        Label(5, 6, TAG_HEIGHT_MM, "CD"),
        Label(32, -12, TAG_HEIGHT_MM, "CA"),
        Label(2, 17.5, TEXT_HEIGHT_MM, "A"),
        Label(2, -22, TEXT_HEIGHT_MM, "B"),
    ),
    attdefs=(
        *_common(tag_xy=(0, 47.5), desc_xy=(0, 43)),
        AttDef("MFR", "Fabricante", 0, 39),
        AttDef("MODEL", "Modelo", 0, 35),
        *_hidden(
            ("PAC_W", "Potencia CA nominal (W)"),
            ("VAC_V", "Tensión CA nominal (V)"),
            ("PHASES", "Conductores energizados"),
            ("IAC_MAX_A", "Corriente CA máxima (A)"),
            ("VDC_MAX_V", "Tensión CD máxima (V)"),
            ("MPPT_N", "Número de MPPT"),
            ("OCPD_MAX_A", "Protección máxima CA (A)"),
            ("ISOLATION", "Aislamiento"),
            ("CERT", "Certificaciones"),
            ("DC_SWITCH", "Desconectador CD integrado"),
            ("DC_SPD", "DPS CD integrado"),
        ),
    ),
    ports=(
        Port("A", 0, 20, "left", "DC"),
        Port("B", 0, -20, "left", "DC", required=False),
        Port("AC", 45, 0, "right", "AC"),
        Port("PE", 22.5, -32.5, "down", "PE"),
    ),
)

BREAKER = SymbolDef(
    name="PVSLD_CB",
    function="Interruptor termomagnético",
    description_es="Interruptor termomagnético (ITM)",
    iec_ref="IEC 60617 S00287",
    layer=_EQ_AC,
    geometry=(
        Line(0, 0, 5, 0, _EQ_AC),
        Line(5, 0, 10, 5, _EQ_AC),
        Line(10, 0, 15, 0, _EQ_AC),
        Line(8.5, 3.5, 11.5, 6.5, _EQ_AC),
        Line(8.5, 6.5, 11.5, 3.5, _EQ_AC),
    ),
    attdefs=(
        *_common(tag_xy=(0, 13), desc_xy=(0, -6.5)),
        AttDef("ROLE", "Función (I1, I2)", 0, 9.5),
        *_hidden(
            ("POLES", "Polos"),
            ("RATING_A", "Corriente nominal (A)"),
            ("VOLT_V", "Tensión (V)"),
            ("KAIC_KA", "Capacidad interruptiva (kA)"),
            ("BACKFED", "Alimentado en sentido inverso"),
        ),
    ),
    ports=(Port("IN", 0, 0, "left", "AC"), Port("OUT", 15, 0, "right", "AC")),
)

POINT_OF_INTERCONNECTION = SymbolDef(
    name="PVSLD_PI",
    function="Punto de interconexión",
    description_es="Punto de interconexión (PI) con la red de distribución",
    iec_ref=NO_IEC_REF,
    layer=_EQ_UT,
    geometry=(Circle(5, 0, 5, _EQ_UT), Circle(5, 0, 1.5, _EQ_UT)),
    attdefs=(
        *_common(tag_xy=(0, 7.5), desc_xy=(-20, -10.5)),
        *_hidden(
            ("PI_TYPE", "Tipo de conexión"),
            ("PANEL", "Tablero de conexión"),
            ("BREAKER", "Interruptor de conexión"),
        ),
    ),
    ports=(Port("IN", 0, 0, "left", "AC"), Port("OUT", 10, 0, "right", "AC")),
)

PANEL = SymbolDef(
    name="PVSLD_PANEL",
    function="Centro de carga",
    description_es="Centro de carga o tablero con barra",
    iec_ref="IEC 60617 S00062",
    layer=_EQ_AC,
    geometry=(
        Polyline(((0, -27.5), (45, -27.5), (45, 27.5), (0, 27.5)), layers.ENCLOSURES, closed=True),
        Line(0, 0, 45, 0, _EQ_AC),
        Line(22.5, -15, 22.5, 22.5, layers.AC_CONDUCTORS, lineweight=70),
        Line(12.5, -22.5, 32.5, -22.5, layers.GROUNDING),
        Line(22.5, -27.5, 22.5, -22.5, layers.GROUNDING),
    ),
    attdefs=(
        *_common(tag_xy=(0, 40), desc_xy=(0, 35.5)),
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
    ports=(
        Port("LEFT", 0, 0, "left", "AC"),
        Port("RIGHT", 45, 0, "right", "AC"),
        Port("PE", 22.5, -27.5, "down", "PE"),
    ),
)

METER = SymbolDef(
    name="PVSLD_METER",
    function="Medidor",
    description_es="Medidor de energía bidireccional",
    iec_ref="IEC 60617 S00937",
    layer=_EQ_UT,
    geometry=(Circle(7.5, 0, 7.5, _EQ_UT), Label(4.5, -1.3, TEXT_HEIGHT_MM, "kWh")),
    attdefs=(
        *_common(tag_xy=(0, 10.5), desc_xy=(-8, -14.5)),
        *_hidden(
            ("METER_TYPE", "Tipo (MF, MCE)"),
            ("BIDIRECTIONAL", "Bidireccional"),
            ("OWNER", "Propietario"),
            ("METER_NO", "Número de medidor"),
        ),
    ),
    ports=(Port("IN", 0, 0, "left", "AC"), Port("OUT", 15, 0, "right", "AC")),
)

GRID = SymbolDef(
    name="PVSLD_GRID",
    function="Red de distribución",
    description_es="Red de distribución del suministrador",
    iec_ref=NO_IEC_REF,
    layer=_EQ_UT,
    geometry=(
        Polyline(((0, -10), (25, -10), (25, 10), (0, 10)), _EQ_UT, closed=True),
        Label(3.5, -1.5, TAG_HEIGHT_MM, "RED"),
    ),
    attdefs=(
        *_common(tag_xy=(0, 12.5), desc_xy=(0, -18.5)),
        AttDef("SPEC", "Tensión y sistema", 0, -22.5),
        *_hidden(
            ("VOLT_V", "Tensión nominal (V)"),
            ("SYSTEM", "Sistema"),
            ("FREQ_HZ", "Frecuencia (Hz)"),
            ("OWNER", "Suministrador"),
            ("ISC_KA", "Corriente de falla disponible (kA)"),
        ),
    ),
    ports=(Port("IN", 0, 0, "left", "AC"),),
)

GROUND = SymbolDef(
    name="PVSLD_GND",
    function="Electrodo de puesta a tierra",
    description_es="Electrodo de puesta a tierra",
    iec_ref="IEC 60617 S00200",
    layer=layers.GROUNDING,
    geometry=(
        Line(0, 0, 0, -5, layers.GROUNDING),
        Line(-6, -5, 6, -5, layers.GROUNDING),
        Line(-4, -7.5, 4, -7.5, layers.GROUNDING),
        Line(-2, -10, 2, -10, layers.GROUNDING),
    ),
    attdefs=(
        *_common(tag_xy=(9, -6), desc_xy=(9, -10.5)),
        AttDef("SPEC", "Electrodo y resistencia", 9, -14.5),
        *_hidden(
            ("ELECTRODE", "Tipo de electrodo"),
            ("R_OHM", "Resistencia de diseño (Ω)"),
            ("GEC_SIZE", "Calibre del conductor al electrodo"),
        ),
    ),
    ports=(Port("PE", 0, 0, "up", "PE"),),
)

# Title block (pie de plano): 185 x 60 mm, six rows of ten millimetres. Each field is
# (tag, caption, x0, x1, row from the top, value height).
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


def _title_block_geometry() -> tuple[Primitive, ...]:
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
    return tuple(items)


def _title_block_attdefs() -> tuple[AttDef, ...]:
    frame = layers.TITLE_BLOCK
    attdefs = [
        AttDef(
            tag,
            caption.title(),
            x0 + 1.5,
            TITLE_BLOCK_HEIGHT_MM - row * TITLE_BLOCK_ROW_MM - 8.8,
            height,
            layer=frame,
        )
        for tag, caption, x0, _x1, row, height in TITLE_BLOCK_FIELDS
    ]
    attdefs += [
        AttDef("COMP_ID", "Identificador en el modelo", 0, 0, visible=False, layer=frame),
        AttDef("IEC_REF", "Referencia IEC 60617", 0, 0, visible=False, layer=frame),
        AttDef("NMX_REF", "Referencia NMX-J-136-ANCE", 0, 0, visible=False, layer=frame),
        AttDef("TAG", "Identificador", 0, 0, visible=False, layer=frame),
        AttDef("DESC", "Descripción", 0, 0, visible=False, layer=frame),
    ]
    return tuple(attdefs)


TITLE_BLOCK = SymbolDef(
    name="PVSLD_TTLB",
    function="Cuadro de datos del plano",
    description_es="Cuadro de datos del plano (pie de plano)",
    iec_ref=NO_IEC_REF,
    layer=layers.TITLE_BLOCK,
    geometry=_title_block_geometry(),
    attdefs=_title_block_attdefs(),
    ports=(),
    nmx_ref="NMX-J-136-ANCE Sección 5",
)

SYMBOLS: Mapping[str, SymbolDef] = {
    symbol.name: symbol
    for symbol in (
        PV_STRING,
        INVERTER,
        BREAKER,
        POINT_OF_INTERCONNECTION,
        PANEL,
        METER,
        GRID,
        GROUND,
        TITLE_BLOCK,
    )
}


def get_symbol(name: str) -> SymbolDef:
    """Return the symbol called ``name``.

    Raises:
        KeyError: the library has no such block.
    """
    try:
        return SYMBOLS[name]
    except KeyError:
        raise KeyError(f"unknown symbol {name!r}; library has {', '.join(SYMBOLS)}") from None


def symbol_catalogue() -> list[dict[str, object]]:
    """The whole library as plain data (``pvsld://symbols`` resource, documentation)."""
    return [symbol.to_dict() for symbol in SYMBOLS.values()]
