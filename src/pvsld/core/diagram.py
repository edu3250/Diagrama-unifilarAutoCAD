"""Backend-neutral diagram model (ADR-0001, layer L2).

A :class:`Diagram` is the complete description of one sheet in **sheet millimetres** (origin at the
bottom-left corner of the paper, x to the right, y up): which symbol is inserted where with which
attribute values, which conductor joins which ports along which route, every text, table and
frame line, the title block and the layer of each item. Render backends only materialize it; they
decide no layout. That keeps the ezdxf backend and the future AutoCAD backend in parity and makes
the result testable without any CAD.

Everything is immutable and ordered, and every coordinate is rounded to 0.001 mm, so building the
same diagram twice yields equal objects (and, downstream, byte-identical files).

Two spaces mirror a CAD file: ``"model"`` holds the schematic, tables and notes; ``"paper"`` holds
the sheet furniture (border, title block, revision block). A single 1:1 viewport on the paper
sheet shows the model, so model and paper coordinates coincide.
"""

from __future__ import annotations

import unicodedata
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Literal

from pvsld.core import layers
from pvsld.symbols import get_symbol

Space = Literal["model", "paper"]
ConnectionKind = Literal["pv_source", "inverter_output", "ac_network", "grounding"]
Align = Literal["left", "center"]

PORT_TOLERANCE_MM = 0.01
"""A wire end must lie within this distance of the port it connects (ADR-0001, S1 criteria)."""
CAP_HEIGHT_RATIO = 0.716
"""Arial cap height over its em size. A DXF text ``height`` is the cap height."""
WIDTH_SAFETY = 1.03
"""Margin over the nominal advance widths (kerning-free sums, other fonts on other systems)."""

# Arial advance widths in 1/1000 em for printable ASCII (identical to Helvetica's metrics).
_ARIAL_ASCII = (
    "278 278 355 556 556 889 667 191 333 333 389 584 278 333 278 278 "  # space to /
    "556 556 556 556 556 556 556 556 556 556 278 278 584 584 584 556 "  # 0-9 : ; < = > ?
    "1015 667 667 722 722 667 611 778 722 278 500 667 556 833 722 778 "  # @ A-O
    "667 778 722 667 611 722 667 944 667 667 611 278 278 278 469 556 "  # P-Z [ \ ] ^ _
    "333 556 556 500 556 556 278 556 556 222 222 500 222 833 556 556 "  # ` a-o
    "556 556 333 500 278 556 500 722 500 500 500 334 260 334 584"  # p-z { | } ~
)
_ARIAL_WIDTHS = {chr(32 + i): int(w) for i, w in enumerate(_ARIAL_ASCII.split())}
_SPECIAL_WIDTHS = {
    "β": 575,
    "γ": 500,
    "Δ": 612,
    "Ω": 807,
    "×": 584,
    "≤": 549,
    "°": 400,
    "²": 333,
    "—": 1000,
    "·": 278,
}
_DEFAULT_WIDTH = 600


def _glyph_width(char: str) -> int:
    if char in _ARIAL_WIDTHS:
        return _ARIAL_WIDTHS[char]
    if char in _SPECIAL_WIDTHS:
        return _SPECIAL_WIDTHS[char]
    base = unicodedata.normalize("NFD", char)[0]  # accented letters have their base width
    return _ARIAL_WIDTHS.get(base, _DEFAULT_WIDTH)


def rnd(value: float) -> float:
    """Round to 0.001 mm (and avoid ``-0.0``), the precision of every coordinate."""
    result = round(value, 3)
    return 0.0 if result == 0 else result


def text_width_mm(text: str, height: float) -> float:
    """Estimated width of ``text`` set in Arial at cap height ``height``.

    Used for fit and overlap checks and for sizing table columns, never for drawing. Sums real
    Arial advance widths, so it tracks what AutoCAD and the ezdxf preview render.
    """
    em = height / CAP_HEIGHT_RATIO
    return sum(_glyph_width(char) for char in text) / 1000 * em * WIDTH_SAFETY


@dataclass(frozen=True)
class Point:
    x: float
    y: float


@dataclass(frozen=True)
class Box:
    """Axis-aligned rectangle ``(x0, y0)-(x1, y1)`` with ``x0 <= x1`` and ``y0 <= y1``."""

    x0: float
    y0: float
    x1: float
    y1: float

    def intersects(self, other: Box, *, gap: float = 0.0) -> bool:
        return (
            self.x0 < other.x1 + gap
            and other.x0 < self.x1 + gap
            and self.y0 < other.y1 + gap
            and other.y0 < self.y1 + gap
        )

    def contains(self, other: Box) -> bool:
        return (
            self.x0 <= other.x0
            and self.y0 <= other.y0
            and other.x1 <= self.x1
            and other.y1 <= self.y1
        )

    def union(self, other: Box) -> Box:
        return Box(
            min(self.x0, other.x0),
            min(self.y0, other.y0),
            max(self.x1, other.x1),
            max(self.y1, other.y1),
        )


@dataclass(frozen=True)
class PortRef:
    """``COMP_ID`` plus port id, written ``S1.OUT`` in the drawing data."""

    comp_id: str
    port: str

    def __str__(self) -> str:
        return f"{self.comp_id}.{self.port}"

    @classmethod
    def parse(cls, text: str) -> PortRef:
        comp_id, _, port = text.rpartition(".")
        if not comp_id or not port:
            raise ValueError(f"not a port reference: {text!r}")
        return cls(comp_id, port)


@dataclass(frozen=True)
class SymbolInstance:
    """One component: an INSERT of a library block with attribute values."""

    comp_id: str
    symbol: str
    x: float
    y: float
    layer: str
    attributes: tuple[tuple[str, str], ...]
    space: Space = "model"

    @property
    def values(self) -> dict[str, str]:
        return dict(self.attributes)

    def port_xy(self, port_id: str) -> Point:
        """World position of a port (blocks are inserted unrotated at scale 1)."""
        port = get_symbol(self.symbol).port(port_id)
        return Point(rnd(self.x + port.x), rnd(self.y + port.y))

    def boxes(self) -> list[tuple[str, Box]]:
        """Named boxes of this instance: its geometry and each visible attribute text."""
        symbol = get_symbol(self.symbol)
        x0, y0, x1, y1 = symbol.bounds()
        result = [
            (
                f"{self.comp_id} symbol",
                Box(rnd(self.x + x0), rnd(self.y + y0), rnd(self.x + x1), rnd(self.y + y1)),
            )
        ]
        values = self.values
        for attdef in symbol.attdefs:
            text = values.get(attdef.tag)
            if attdef.visible and text:
                x0 = self.x + attdef.x
                y0 = self.y + attdef.y
                result.append(
                    (
                        f"{self.comp_id}.{attdef.tag}",
                        Box(
                            rnd(x0),
                            rnd(y0),
                            rnd(x0 + text_width_mm(text, attdef.height)),
                            rnd(y0 + attdef.height),
                        ),
                    )
                )
        return result

    def box(self) -> Box:
        """Bounding box of the geometry and of every visible attribute text together."""
        boxes = [box for _, box in self.boxes()]
        merged = boxes[0]
        for box in boxes[1:]:
            merged = merged.union(box)
        return merged


@dataclass(frozen=True)
class Connection:
    """A conductor drawn between two ports along ``points`` (first and last lie on the ports)."""

    id: str
    kind: ConnectionKind
    layer: str
    start: PortRef
    end: PortRef
    points: tuple[Point, ...]
    circuit_id: str | None = None


@dataclass(frozen=True)
class TextItem:
    """A single-line text: ``(x, y)`` is the left end of its baseline, or its centre if centred.

    ``style`` names a text style of the sheet template (:attr:`Diagram.text_styles`); ``None`` is
    the house style.
    """

    layer: str
    x: float
    y: float
    height: float
    text: str
    space: Space = "model"
    style: str | None = None
    align: Align = "left"

    def box(self) -> Box:
        width = text_width_mm(self.text, self.height)
        if self.align == "center":
            x0, y0 = self.x - width / 2, self.y - self.height / 2
        else:
            x0, y0 = self.x, self.y
        return Box(rnd(x0), rnd(y0), rnd(x0 + width), rnd(y0 + self.height))


@dataclass(frozen=True)
class LineItem:
    layer: str
    x1: float
    y1: float
    x2: float
    y2: float
    space: Space = "model"
    lineweight: int | None = None


@dataclass(frozen=True)
class PolylineItem:
    layer: str
    points: tuple[Point, ...]
    closed: bool = False
    space: Space = "model"
    lineweight: int | None = None


@dataclass(frozen=True)
class CircleItem:
    layer: str
    cx: float
    cy: float
    radius: float
    space: Space = "model"


@dataclass(frozen=True)
class SymbolSample:
    """A scaled INSERT of a library block with no identity (a symbology table entry).

    Unlike a :class:`SymbolInstance` it stands for no component: no attribute values, no ports to
    connect, not counted as equipment.
    """

    symbol: str
    x: float
    y: float
    scale: float
    layer: str
    space: Space = "paper"


@dataclass(frozen=True)
class Table:
    """A ruled table: a title row, a header row and data rows, anchored at its top-left corner."""

    id: str
    layer: str
    x: float
    y_top: float
    col_widths: tuple[float, ...]
    title: str
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    row_height: float = 5.0
    text_height: float = 2.5
    space: Space = "model"
    style: str | None = None
    """Text style of the cells (``None``: the house style)."""
    title_style: str | None = None
    title_center: bool = False
    """Centre the title in its row (the owner's sheet template boxes)."""
    title_height: float | None = None
    """Height of the title text (default ``text_height``)."""

    @property
    def width(self) -> float:
        return rnd(sum(self.col_widths))

    @property
    def height(self) -> float:
        return rnd(self.row_height * (2 + len(self.rows)))

    def box(self) -> Box:
        return Box(self.x, rnd(self.y_top - self.height), rnd(self.x + self.width), self.y_top)

    def cells(self) -> Iterator[tuple[float, str]]:
        """Yield ``(column width, text)`` of every non-title cell (for fit checks)."""
        for row in (self.header, *self.rows):
            yield from zip(self.col_widths, row, strict=True)

    def lines(self) -> list[LineItem]:
        """Frame, row rules and column rules (the title row has no column rules)."""
        x0, x1 = self.x, rnd(self.x + self.width)
        y_bottom = rnd(self.y_top - self.height)
        items = [
            LineItem(self.layer, x0, self.y_top, x1, self.y_top, self.space),
            LineItem(self.layer, x1, self.y_top, x1, y_bottom, self.space),
            LineItem(self.layer, x1, y_bottom, x0, y_bottom, self.space),
            LineItem(self.layer, x0, y_bottom, x0, self.y_top, self.space),
        ]
        for row in range(1, 2 + len(self.rows)):
            y = rnd(self.y_top - row * self.row_height)
            items.append(LineItem(self.layer, x0, y, x1, y, self.space))
        x = x0
        for width in self.col_widths[:-1]:
            x = rnd(x + width)
            items.append(
                LineItem(self.layer, x, rnd(self.y_top - self.row_height), x, y_bottom, self.space)
            )
        return items

    def texts(self) -> list[TextItem]:
        pad_x, pad_y = 1.5, (self.row_height - self.text_height) / 2
        if self.title_center:
            title = TextItem(
                self.layer,
                rnd(self.x + self.width / 2),
                rnd(self.y_top - self.row_height / 2),
                self.title_height or self.text_height,
                self.title,
                self.space,
                style=self.title_style or self.style,
                align="center",
            )
        else:
            title = TextItem(
                self.layer,
                rnd(self.x + pad_x),
                rnd(self.y_top - self.row_height + pad_y),
                self.title_height or self.text_height,
                self.title,
                self.space,
                style=self.title_style or self.style,
            )
        items = [title]
        for index, row in enumerate((self.header, *self.rows), start=1):
            y = rnd(self.y_top - (index + 1) * self.row_height + pad_y)
            x = self.x
            for width, text in zip(self.col_widths, row, strict=True):
                if text:
                    items.append(
                        TextItem(
                            self.layer,
                            rnd(x + pad_x),
                            y,
                            self.text_height,
                            text,
                            self.space,
                            style=self.style,
                        )
                    )
                x = rnd(x + width)
        return items


@dataclass(frozen=True)
class Viewport:
    """Paper-space window onto the model, at scale 1:1 (``view_height == size[1]``)."""

    center: Point
    size: tuple[float, float]
    view_center: Point
    view_height: float
    layer: str = layers.NON_PLOT


@dataclass(frozen=True)
class Sheet:
    """Paper size and the border rectangle."""

    name: str
    width: float
    height: float
    border: Box


A3 = Sheet("A3", 420.0, 297.0, Box(10.0, 10.0, 410.0, 287.0))


@dataclass(frozen=True)
class Diagram:
    """The whole sheet; see the module docstring."""

    sheet: Sheet
    template: str
    metadata: tuple[tuple[str, str], ...]
    instances: tuple[SymbolInstance, ...]
    connections: tuple[Connection, ...]
    texts: tuple[TextItem, ...]
    lines: tuple[LineItem, ...]
    polylines: tuple[PolylineItem, ...]
    tables: tuple[Table, ...]
    viewport: Viewport
    circles: tuple[CircleItem, ...] = ()
    samples: tuple[SymbolSample, ...] = ()
    text_styles: tuple[tuple[str, str], ...] = ()
    """Text styles of a sheet template as ``(name, font file)``."""

    def instance(self, comp_id: str) -> SymbolInstance:
        for item in self.instances:
            if item.comp_id == comp_id:
                return item
        raise KeyError(f"no component {comp_id!r}")

    def block_counts(self) -> dict[str, int]:
        """Number of INSERTs per block name (the S1 criterion compares this with the DXF).

        Symbology samples are INSERTs too; they carry no ``COMP_ID``.
        """
        return dict(
            Counter([*(i.symbol for i in self.instances), *(s.symbol for s in self.samples)])
        )

    def used_layers(self) -> set[str]:
        used = {i.layer for i in self.instances} | {c.layer for c in self.connections}
        used |= {t.layer for t in self.texts} | {item.layer for item in self.lines}
        used |= {p.layer for p in self.polylines} | {t.layer for t in self.tables}
        used |= {c.layer for c in self.circles} | {s.layer for s in self.samples}
        used.add(self.viewport.layer)
        return used


def _known(name: str) -> bool:
    try:
        get_symbol(name)
    except KeyError:
        return False
    return True


def check_diagram(diagram: Diagram) -> list[str]:
    """Structural problems of a diagram (empty list when sound).

    Checks identity, attribute completeness, layer standard, that every wire end lies on the port
    it names and that every required port is connected at least once.
    """
    problems: list[str] = []
    ids = Counter(i.comp_id for i in diagram.instances)
    problems += [f"duplicate COMP_ID {name}" for name, count in ids.items() if count > 1]

    for item in diagram.instances:
        try:
            symbol = get_symbol(item.symbol)
        except KeyError:
            problems.append(f"{item.comp_id}: unknown symbol {item.symbol}")
            continue
        tags = [tag for tag, _ in item.attributes]
        if tags != list(symbol.tags):
            problems.append(f"{item.comp_id}: attributes {tags} differ from {list(symbol.tags)}")
        if item.values.get("COMP_ID") != item.comp_id:
            problems.append(f"{item.comp_id}: COMP_ID attribute does not match")

    unknown = sorted(diagram.used_layers() - layers.LAYER_NAMES)
    if unknown:
        problems.append(f"layers outside the house standard: {', '.join(unknown)}")

    connected: Counter[str] = Counter()
    for conn in diagram.connections:
        for ref, point in ((conn.start, conn.points[0]), (conn.end, conn.points[-1])):
            try:
                expected = diagram.instance(ref.comp_id).port_xy(ref.port)
            except KeyError as error:
                problems.append(f"{conn.id}: {error.args[0]}")
                continue
            if (
                abs(expected.x - point.x) > PORT_TOLERANCE_MM
                or abs(expected.y - point.y) > PORT_TOLERANCE_MM
            ):
                problems.append(f"{conn.id}: end is not on port {ref}")
            connected[str(ref)] += 1
        for a, b in zip(conn.points, conn.points[1:], strict=False):
            if a.x != b.x and a.y != b.y:
                problems.append(f"{conn.id}: diagonal segment {a} -> {b}")

    for item in diagram.instances:
        if not _known(item.symbol):
            continue
        for port in get_symbol(item.symbol).ports:
            if port.required and connected[f"{item.comp_id}.{port.id}"] == 0:
                problems.append(f"{item.comp_id}.{port.id} is a dangling required port")
    return problems
