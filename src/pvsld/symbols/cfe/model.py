"""Data model of the CFE symbol library (ADR-0005): geometry primitives, ports, attributes, symbols.

A :class:`SymbolSpec` is a plain, immutable description of one block. The definitions live in
:mod:`pvsld.symbols.cfe.definitions`; :mod:`pvsld.symbols.cfe.build` turns them into DXF blocks.
Everything is in block-local millimetres, at 1:1, with Y pointing up.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Literal

from pvsld.core import layers

LIBRARY_VERSION = "0.5.0"
"""Semantic version of the library (ADR-0005, section 7); also stored in every block record."""
APP_ID = "PVSLD"
BLOCK_PREFIX = "PVSLD_"
GRID_MM = 2.5
"""Ports sit on this grid (ADR-0003, point 4), so aligning two symbols is arithmetic."""
TEXT_HEIGHT_MM = 2.5
TAG_HEIGHT_MM = 3.5

SOURCE_CFE_C = "CFE G0100-04 Apéndice C"
SOURCE_CFE_D = "CFE G0100-04 Apéndice D"
SOURCE_OWN = "pvsld (sin símbolo en CFE G0100-04 ni IEC 60617)"
SOURCE_PREFIXES: tuple[str, ...] = (
    "CFE G0100-04",
    "NMX-J-136-ANCE",
    "DGE (basada en IEC 60617)",
    "UNE-EN 60617",
    "IEC 60617",
    "pvsld",
)
"""A symbol must name where its shape comes from; these are the accepted families. Priority is
CFE G0100-04, then NMX-J-136-ANCE-2019, then IEC 60617 (here through the Peruvian DGE norm and the
UNE-EN 60617 sheet of the owner); a drawing the sources do not define says ``pvsld``."""

NO_IEC_REF = "-"
NMX_PENDING = "NMX-J-136-ANCE (pendiente)"
"""Placeholder until the purchased NMX-J-136-ANCE text confirms the figure numbers (ADR-0003)."""

PortKind = Literal["DC", "AC", "PE", "SIG", "ANY"]
"""``SIG`` is a signal or control link (dashed line), ``ANY`` a "
"connection that takes any conductor."""
Direction = Literal["left", "right", "up", "down"]

COMMON_TAGS: tuple[str, ...] = ("TAG", "DESC", "COMP_ID", "IEC_REF", "NMX_REF", "SOURCE_STANDARD")
HIDDEN_TAGS: tuple[str, ...] = ("COMP_ID", "IEC_REF", "NMX_REF", "SOURCE_STANDARD")


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
    linetype: str | None = None


@dataclass(frozen=True)
class Polyline:
    points: tuple[tuple[float, float], ...]
    layer: str
    closed: bool = False
    linetype: str | None = None


@dataclass(frozen=True)
class Circle:
    cx: float
    cy: float
    radius: float
    layer: str


@dataclass(frozen=True)
class Arc:
    """Counter-clockwise arc from ``start`` to ``end`` degrees."""

    cx: float
    cy: float
    radius: float
    start: float
    end: float
    layer: str


@dataclass(frozen=True)
class Dot:
    """A filled disc (junction dot); a solid hatch in the DXF."""

    cx: float
    cy: float
    radius: float
    layer: str


@dataclass(frozen=True)
class Fill:
    """A filled polygon (arrowhead); a solid hatch in the DXF."""

    points: tuple[tuple[float, float], ...]
    layer: str


@dataclass(frozen=True)
class Label:
    """Fixed text that is part of the symbol (``kWh`` in the meter); ``(x, y)`` is the baseline."""

    x: float
    y: float
    height: float
    text: str
    layer: str = layers.TAGS


Primitive = Line | Polyline | Circle | Arc | Dot | Fill | Label


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
    legend_sample: str = ""
    """Text shown for this attribute in the legend, where blocks are inserted without values."""


@dataclass(frozen=True)
class SymbolSpec:
    """One block of the library.

    ``attdefs`` already holds the common attributes (``TAG``, ``DESC``, the hidden ``COMP_ID``,
    ``IEC_REF``, ``NMX_REF``, ``SOURCE_STANDARD``) followed by the function-specific ones.
    """

    name: str
    description_es: str
    source: str
    iec_ref: str
    nmx_ref: str
    layer: str
    geometry: tuple[Primitive, ...]
    attdefs: tuple[AttDef, ...]
    ports: tuple[Port, ...]
    note: str = ""
    """Reviewer note: how the drawing relates to its source (shown by ``pvsld symbols list``)."""
    family: str = ""
    """Family heading of the legend (generación, protección, ...)."""

    @property
    def tags(self) -> tuple[str, ...]:
        return tuple(a.tag for a in self.attdefs)

    def port(self, port_id: str) -> Port:
        for port in self.ports:
            if port.id == port_id:
                return port
        raise KeyError(f"symbol {self.name} has no port {port_id!r}")

    def bounds(self) -> tuple[float, float, float, float]:
        """``(xmin, ymin, xmax, ymax)`` of the geometry (text is estimated, attributes ignored)."""
        return bounds_of(self.geometry)

    def to_dict(self) -> dict[str, object]:
        """Plain data for ``pvsld symbols list --json``."""
        return {
            "block": self.name,
            "description_es": self.description_es,
            "source": self.source,
            "family": self.family,
            "iec_ref": self.iec_ref,
            "nmx_ref": self.nmx_ref,
            "version": LIBRARY_VERSION,
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


# --- Geometry helpers ----------------------------------------------------------------------------


def _arc_points(item: Arc, steps: int = 16) -> list[tuple[float, float]]:
    sweep = (item.end - item.start) % 360 or 360
    return [
        (
            item.cx + item.radius * math.cos(math.radians(item.start + sweep * i / steps)),
            item.cy + item.radius * math.sin(math.radians(item.start + sweep * i / steps)),
        )
        for i in range(steps + 1)
    ]


def bounds_of(items: Iterable[Primitive]) -> tuple[float, float, float, float]:
    """``(xmin, ymin, xmax, ymax)`` of ``items`` (text is estimated)."""
    points = [point for item in items for point in _extent_points(item)]
    xs = [x for x, _ in points]
    ys = [y for _, y in points]
    return min(xs), min(ys), max(xs), max(ys)


def _extent_points(item: Primitive) -> list[tuple[float, float]]:
    if isinstance(item, Line):
        return [(item.x1, item.y1), (item.x2, item.y2)]
    if isinstance(item, Polyline | Fill):
        return list(item.points)
    if isinstance(item, Circle | Dot):
        r = item.radius
        return [(item.cx - r, item.cy - r), (item.cx + r, item.cy + r)]
    if isinstance(item, Arc):
        return _arc_points(item)
    width = 0.6 * item.height * len(item.text)
    return [(item.x, item.y), (item.x + width, item.y + item.height)]


def _segment_distance(
    px: float, py: float, a: tuple[float, float], b: tuple[float, float]
) -> float:
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    length_sq = dx * dx + dy * dy
    t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length_sq))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def distance_to_outline(item: Primitive, x: float, y: float) -> float:
    """Distance from ``(x, y)`` to the stroke of ``item`` (infinity for text)."""
    if isinstance(item, Line):
        return _segment_distance(x, y, (item.x1, item.y1), (item.x2, item.y2))
    if isinstance(item, Polyline):
        pts = list(item.points)
        pairs = list(pairwise(pts))
        if item.closed:
            pairs.append((pts[-1], pts[0]))
        return min(_segment_distance(x, y, a, b) for a, b in pairs)
    if isinstance(item, Circle):
        return abs(math.hypot(x - item.cx, y - item.cy) - item.radius)
    if isinstance(item, Arc):
        return min(math.hypot(x - px, y - py) for px, py in _arc_points(item, steps=64))
    if isinstance(item, Dot):
        return max(0.0, math.hypot(x - item.cx, y - item.cy) - item.radius)
    if isinstance(item, Fill):
        pts = list(item.points)
        return min(_segment_distance(x, y, a, b) for a, b in pairwise([*pts, pts[0]]))
    return math.inf


def port_distance(spec: SymbolSpec, port: Port) -> float:
    """Distance from ``port`` to the nearest stroke of the symbol (0 when it touches it)."""
    return min((distance_to_outline(g, port.x, port.y) for g in spec.geometry), default=math.inf)


def _turn(x: float, y: float) -> tuple[float, float]:
    return -y + 0.0, x + 0.0  # + 0.0 turns -0.0 into 0.0 so the file never prints "-0.0"


def rotate90(items: Iterable[Primitive]) -> tuple[Primitive, ...]:
    """Turn geometry 90 degrees counter-clockwise about the origin: ``(x, y) -> (-y, x)``.

    A device drawn vertically (current flowing down from the origin) then flows to the right,
    which is how the diagram runs. Text keeps its orientation; only its anchor moves.
    """
    turned: list[Primitive] = []
    for item in items:
        if isinstance(item, Line):
            x1, y1 = _turn(item.x1, item.y1)
            x2, y2 = _turn(item.x2, item.y2)
            turned.append(replace(item, x1=x1, y1=y1, x2=x2, y2=y2))
        elif isinstance(item, Polyline | Fill):
            turned.append(replace(item, points=tuple(_turn(x, y) for x, y in item.points)))
        elif isinstance(item, Circle | Dot):
            cx, cy = _turn(item.cx, item.cy)
            turned.append(replace(item, cx=cx, cy=cy))
        elif isinstance(item, Arc):
            cx, cy = _turn(item.cx, item.cy)
            turned.append(
                replace(
                    item, cx=cx, cy=cy, start=(item.start + 90) % 360, end=(item.end + 90) % 360
                )
            )
        else:
            x, y = _turn(item.x, item.y)
            turned.append(replace(item, x=x, y=y))
    return tuple(turned)
