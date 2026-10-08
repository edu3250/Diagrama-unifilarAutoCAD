"""Build the symbol library DXF: one ``BLOCK`` per symbol and the ``Legend`` sheet (ADR-0005).

The file is ``symbols/pvsld-symbols.dxf`` (DXF R2018). It holds every block of
:data:`pvsld.symbols.cfe.definitions.LIBRARY` (geometry, ``ATTDEF`` s, port XDATA) and a
paper-space layout ``Legend`` (A3, landscape) with the table *Símbolo | Designación | Fuente*, one
row per block with an ``INSERT`` scaled to fit its cell.

Block record XDATA, application ``PVSLD``, follows ADR-0003: ``pvsld.block/1``, library version,
port count, then six tags per port. One tag is appended after the ports, the source of the symbol;
readers that stop after the port count (:mod:`pvsld.backends.readback`) ignore it.

Determinism. The bytes depend only on the definitions and the ezdxf version: fixed metadata,
sequential handles, a sorted CLASSES section and LF newlines on every platform, like the golden
diagram of Stage 2.1.
"""

from __future__ import annotations

import io
import textwrap
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ezdxf.document import Drawing
from ezdxf.layouts import BaseLayout, BlockLayout
from ezdxf.lldxf import const

from pvsld.backends.dxf import (
    BLOCK_FORMAT,
    PLOT_DEVICE,
    TEXT_STYLE,
    _new_document,
    _sort_class_registration,
    fixed_metadata,
)
from pvsld.core import layers
from pvsld.symbols.cfe.definitions import LIBRARY
from pvsld.symbols.cfe.model import (
    APP_ID,
    LIBRARY_VERSION,
    Arc,
    Circle,
    Dot,
    Fill,
    Label,
    Line,
    Polyline,
    SymbolSpec,
)

LIBRARY_FILE = Path("symbols") / "pvsld-symbols.dxf"
LEGEND_LAYOUT = "Legend"
LEGEND_TITLE = "SIMBOLOGÍA — DIAGRAMAS UNIFILARES FOTOVOLTAICOS"
LEGEND_COLUMNS = ("Símbolo", "Designación", "Fuente")
LEGEND_NOTES = (
    "Símbolos redibujados como geometría vectorial a partir de la norma indicada en la columna "
    "Fuente; ninguna norma se incluye ni se copia.",
    "Cada símbolo es un bloque PVSLD_<FUNCIÓN> con los atributos TAG y DESC y, ocultos, COMP_ID, "
    "IEC_REF, NMX_REF y SOURCE_STANDARD; los puertos están en XDATA (aplicación PVSLD).",
    "Dimensiones en mm a escala 1:1 dentro del bloque; en esta hoja cada símbolo se reduce, si "
    "hace falta, para caber en su celda.",
)
DOTTED = "DOTTED"
DASHDOT_SMALL = "DASHDOT_S"
DASHED_SMALL = "DASHED_S"
DASHDOT2 = "DASHDOT2"

SHEET_WIDTH_MM = 420.0
SHEET_HEIGHT_MM = 297.0
MARGIN_MM = 10.0
GROUP_GAP_MM = 10.0
COLUMN_WIDTHS_MM = (42.0, 74.0, 74.0)
TITLE_BAND_MM = 24.0
HEADER_ROW_MM = 8.0
FOOTER_MM = 22.0
MAX_ROW_MM = 18.0
FAMILY_ROW_MM = 7.0
CELL_PADDING_MM = 4.0
CHAR_WIDTH_FACTOR = 0.76
"""Average glyph width over text height of the sheet font, to wrap text without measuring it."""


def _attribs(
    layer: str, *, weight: int | None = None, linetype: str | None = None
) -> dict[str, Any]:
    attribs: dict[str, Any] = {"layer": layer}
    if weight is not None:
        attribs["lineweight"] = weight
    if linetype is not None:
        attribs["linetype"] = linetype
    return attribs


# --- Blocks ----------------------------------------------------------------------


def block_xdata(spec: SymbolSpec) -> list[tuple[int, Any]]:
    """The block record XDATA of ``spec``: ADR-0003 record plus the source as the last tag."""
    tags: list[tuple[int, Any]] = [
        (1000, BLOCK_FORMAT),
        (1000, LIBRARY_VERSION),
        (1070, len(spec.ports)),
    ]
    for port in spec.ports:
        tags += [
            (1000, port.id),
            (1000, port.kind),
            (1000, port.direction),
            (1040, float(port.x)),
            (1040, float(port.y)),
            (1070, int(port.required)),
        ]
    tags.append((1000, spec.source))
    return tags


def _draw_primitive(block: BlockLayout, item: Any) -> None:
    if isinstance(item, Line):
        block.add_line(
            (item.x1, item.y1),
            (item.x2, item.y2),
            dxfattribs=_attribs(item.layer, weight=item.lineweight, linetype=item.linetype),
        )
    elif isinstance(item, Polyline):
        block.add_lwpolyline(
            list(item.points),
            close=item.closed,
            dxfattribs=_attribs(item.layer, linetype=item.linetype),
        )
    elif isinstance(item, Circle):
        block.add_circle((item.cx, item.cy), item.radius, dxfattribs=_attribs(item.layer))
    elif isinstance(item, Arc):
        block.add_arc(
            (item.cx, item.cy), item.radius, item.start, item.end, dxfattribs=_attribs(item.layer)
        )
    elif isinstance(item, Dot):
        # Two bulge-1 vertices make a circle; the solid hatch fills it.
        hatch = block.add_hatch(color=const.BYLAYER, dxfattribs=_attribs(item.layer))
        hatch.paths.add_polyline_path(
            [(item.cx - item.radius, item.cy, 1), (item.cx + item.radius, item.cy, 1)],
            is_closed=True,
        )
    elif isinstance(item, Fill):
        hatch = block.add_hatch(color=const.BYLAYER, dxfattribs=_attribs(item.layer))
        hatch.paths.add_polyline_path(list(item.points), is_closed=True)
    elif isinstance(item, Label):
        text = block.add_text(
            item.text, height=item.height, dxfattribs={"layer": item.layer, "style": TEXT_STYLE}
        )
        text.set_placement((item.x, item.y))
    else:  # pragma: no cover - the Primitive union is closed
        raise TypeError(f"unsupported primitive {item!r}")


def define_block(doc: Drawing, spec: SymbolSpec) -> BlockLayout:
    """Add the ``BLOCK`` of ``spec``: geometry, attribute definitions and the port XDATA."""
    block = doc.blocks.new(spec.name, base_point=(0, 0))
    for item in spec.geometry:
        _draw_primitive(block, item)
    for attdef in spec.attdefs:
        attribs: dict[str, Any] = {
            "layer": attdef.layer,
            "style": TEXT_STYLE,
            "prompt": attdef.prompt_es,
        }
        if not attdef.visible:
            attribs["flags"] = const.ATTRIB_INVISIBLE
        block.add_attdef(
            attdef.tag,
            (attdef.x, attdef.y),
            text=attdef.default,
            height=attdef.height,
            dxfattribs=attribs,
        )
    block.block_record.set_xdata(APP_ID, block_xdata(spec))
    return block


# --- Legend ----------------------------------------------------------------------


def _text(target: BaseLayout, layer: str, x: float, y: float, height: float, text: str) -> None:
    target.add_text(
        text, height=height, dxfattribs={"layer": layer, "style": TEXT_STYLE}
    ).set_placement((x, y))


def _wrap(text: str, width_mm: float, height: float) -> list[str]:
    chars = max(8, int(width_mm / (CHAR_WIDTH_FACTOR * height)))
    return textwrap.wrap(text, chars) or [""]


@dataclass(frozen=True)
class LegendRow:
    """One row of the legend: a family heading or a symbol."""

    heading: str | None = None
    spec: SymbolSpec | None = None

    @property
    def height(self) -> float:
        return FAMILY_ROW_MM if self.heading is not None else MAX_ROW_MM


def legend_layout_name(sheet: int) -> str:
    """``Legend``, ``Legend2``, ``Legend3``... (no space: a Core Console script needs one word)."""
    return LEGEND_LAYOUT if sheet == 1 else f"{LEGEND_LAYOUT}{sheet}"


def legend_pages(specs: Sequence[SymbolSpec]) -> list[list[list[LegendRow]]]:
    """Split the legend into sheets of two column groups, keeping the families together.

    Rows follow ``specs`` (already ordered by family). A heading is never the last row of a
    group, and a family that continues in the next group repeats its heading with ``(cont.)``.
    """
    capacity = SHEET_HEIGHT_MM - 2 * MARGIN_MM - TITLE_BAND_MM - HEADER_ROW_MM - FOOTER_MM
    groups: list[list[LegendRow]] = [[]]
    used = 0.0
    family: str | None = None
    for spec in specs:
        row = LegendRow(spec=spec)
        new_family = spec.family != family
        heading = spec.family or "Otros"
        need = row.height + (FAMILY_ROW_MM if new_family else 0.0)
        if new_family:
            need += row.height  # a heading needs at least one symbol below it
        if used + need > capacity or (not new_family and used + row.height > capacity):
            groups.append([])
            used = 0.0
            if not new_family:
                groups[-1].append(LegendRow(heading=f"{heading} (cont.)"))
                used += FAMILY_ROW_MM
        if new_family:
            groups[-1].append(LegendRow(heading=heading))
            used += FAMILY_ROW_MM
            family = spec.family
        groups[-1].append(row)
        used += row.height
    return [groups[i : i + 2] for i in range(0, len(groups), 2)]


def _fit(spec: SymbolSpec, cell_w: float, cell_h: float) -> tuple[float, float, float]:
    """Scale (at most 1:1) and the insertion point that centre ``spec`` in a cell at the origin."""
    x0, y0, x1, y1 = spec.bounds()
    width, height = max(x1 - x0, 1e-6), max(y1 - y0, 1e-6)
    scale = min(
        1.0, (cell_w - 2 * CELL_PADDING_MM) / width, (cell_h - 2 * CELL_PADDING_MM) / height
    )
    scale = round(scale, 3)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    return scale, round(cell_w / 2 - scale * cx, 4), round(cell_h / 2 - scale * cy, 4)


def _new_sheet(doc: Drawing, sheet: int) -> BaseLayout:
    name = legend_layout_name(sheet)
    if sheet == 1:
        doc.layouts.rename("Layout1", name)
        paper = doc.layouts.get(name)
    else:
        paper = doc.layouts.new(name)
    paper.page_setup(
        size=(SHEET_WIDTH_MM, SHEET_HEIGHT_MM),
        margins=(0, 0, 0, 0),
        units="mm",
        offset=(0, 0),
        rotation=0,
        scale=16,
        name="ISO_full_bleed_A3",
        device=PLOT_DEVICE,
    )
    # The overall paper-space viewport is the one entity AutoCAD requires on layer 0.
    paper.reset_main_viewport().dxf.layer = layers.OVERALL_VIEWPORT
    return paper


def _build_legend(doc: Drawing, specs: Sequence[SymbolSpec]) -> None:
    pages = legend_pages(specs)
    frame, tables, notes = layers.TITLE_BLOCK, layers.TABLES, layers.NOTES
    group_w = sum(COLUMN_WIDTHS_MM)
    top = SHEET_HEIGHT_MM - MARGIN_MM
    table_top = top - TITLE_BAND_MM
    for sheet, groups in enumerate(pages, start=1):
        paper = _new_sheet(doc, sheet)
        paper.add_lwpolyline(
            [
                (MARGIN_MM, MARGIN_MM),
                (SHEET_WIDTH_MM - MARGIN_MM, MARGIN_MM),
                (SHEET_WIDTH_MM - MARGIN_MM, SHEET_HEIGHT_MM - MARGIN_MM),
                (MARGIN_MM, SHEET_HEIGHT_MM - MARGIN_MM),
            ],
            close=True,
            dxfattribs=_attribs(frame, weight=70),
        )
        _text(paper, frame, MARGIN_MM + 5, top - 10, 6, LEGEND_TITLE)
        _text(
            paper,
            notes,
            MARGIN_MM + 5,
            top - 18,
            3.5,
            f"Biblioteca de símbolos pvsld v{LIBRARY_VERSION} — {len(specs)} bloques — "
            f"hoja {sheet} de {len(pages)} — DXF R2018",
        )
        for group, rows in enumerate(groups):
            x0 = MARGIN_MM + 5 + group * (group_w + GROUP_GAP_MM)
            xs = [x0]
            for width in COLUMN_WIDTHS_MM:
                xs.append(xs[-1] + width)
            body = table_top - HEADER_ROW_MM
            bottom = body - sum(row.height for row in rows)
            paper.add_lwpolyline(
                [(xs[0], table_top), (xs[-1], table_top), (xs[-1], bottom), (xs[0], bottom)],
                close=True,
                dxfattribs=_attribs(tables),
            )
            paper.add_line((xs[0], body), (xs[-1], body), dxfattribs=_attribs(tables))
            for column, title in enumerate(LEGEND_COLUMNS):
                _text(paper, notes, xs[column] + 3, table_top - 5.5, 3.5, title)
            y = body
            for row in rows:
                row_top, y = y, y - row.height
                paper.add_line((xs[0], y), (xs[-1], y), dxfattribs=_attribs(tables))
                if row.heading is not None:
                    _text(paper, notes, xs[0] + 3, row_top - 5, 3.5, row.heading.upper())
                else:
                    assert row.spec is not None
                    for x in xs[1:-1]:
                        paper.add_line((x, row_top), (x, y), dxfattribs=_attribs(tables))
                    _legend_row(paper, row.spec, xs, row_top, row.height)
        y = MARGIN_MM + FOOTER_MM - 4
        for note in LEGEND_NOTES:
            for wrapped in _wrap(note, SHEET_WIDTH_MM - 2 * MARGIN_MM - 10, 2.5):
                _text(paper, notes, MARGIN_MM + 5, y, 2.5, wrapped)
                y -= 3.6


def _legend_row(
    paper: BaseLayout, spec: SymbolSpec, xs: Sequence[float], row_top: float, row_h: float
) -> None:
    cell_w = COLUMN_WIDTHS_MM[0]
    scale, dx, dy = _fit(spec, cell_w, row_h)
    ix, iy = round(xs[0] + dx, 4), round(row_top - row_h + dy, 4)
    ref = paper.add_blockref(
        spec.name,
        (ix, iy),
        dxfattribs={"layer": layers.NOTES, "xscale": scale, "yscale": scale, "zscale": scale},
    )
    for attdef in spec.attdefs:
        if attdef.legend_sample:
            ref.add_attrib(
                attdef.tag,
                attdef.legend_sample,
                insert=(round(ix + scale * attdef.x, 4), round(iy + scale * attdef.y, 4)),
                dxfattribs={
                    "layer": attdef.layer,
                    "style": TEXT_STYLE,
                    "height": round(attdef.height * scale, 4),
                },
            )
    y = row_top - 6.0
    for line in _wrap(spec.description_es, COLUMN_WIDTHS_MM[1] - 6, 3.2):
        _text(paper, layers.NOTES, xs[1] + 3, y, 3.2, line)
        y -= 4.4
    _text(paper, layers.NOTES, xs[1] + 3, y - 0.2, 2.2, spec.name)
    y = row_top - 6.0
    for line in _wrap(spec.source, COLUMN_WIDTHS_MM[2] - 6, 2.4):
        _text(paper, layers.NOTES, xs[2] + 3, y, 2.4, line)
        y -= 3.5


# --- Document and bytes ----------------------------------------------------------------------


def build_document(specs: Iterable[SymbolSpec] = LIBRARY) -> Drawing:
    """The library as an in-memory ezdxf document: every block and the ``Legend`` layout."""
    chosen = tuple(specs)
    doc = _new_document()
    doc.linetypes.add(DOTTED, pattern=[1.5, 0.0, -1.5], description="Dotted .  .  .  .")
    doc.linetypes.add(
        DASHDOT_SMALL, pattern=[8.0, 5.0, -1.5, 0.0, -1.5], description="Dash dot (small) _ . _ ."
    )
    doc.linetypes.add(DASHED_SMALL, pattern=[2.0, 1.2, -0.8], description="Dashed (small) __ __")
    doc.linetypes.add(
        DASHDOT2,
        pattern=[14.0, 8.0, -2.0, 0.0, -2.0, 0.0, -2.0],
        description="Dash dot dot __ . . __ . .",
    )
    for spec in chosen:
        define_block(doc, spec)
    _build_legend(doc, chosen)
    doc.layouts.set_active_layout(LEGEND_LAYOUT)
    doc.header["$TILEMODE"] = 0  # open on the Legend, not on the empty Model tab
    doc.header["$LIMMIN"] = (0.0, 0.0)
    doc.header["$LIMMAX"] = (SHEET_WIDTH_MM, SHEET_HEIGHT_MM)
    doc.header["$EXTMIN"] = (MARGIN_MM, MARGIN_MM, 0.0)
    doc.header["$EXTMAX"] = (SHEET_WIDTH_MM - MARGIN_MM, SHEET_HEIGHT_MM - MARGIN_MM, 0.0)
    doc.header["$PROJECTNAME"] = "pvsld-symbols"
    doc.ezdxf_metadata()["PVSLD_LIBRARY_VERSION"] = LIBRARY_VERSION
    _sort_class_registration(doc)
    return doc


def render_library(specs: Iterable[SymbolSpec] = LIBRARY) -> bytes:
    """The bytes of ``pvsld-symbols.dxf``: UTF-8, LF newlines, identical on every platform."""
    with fixed_metadata(True):
        doc = build_document(specs)
        stream = io.StringIO()
        doc.write(stream)
        return doc.encode(stream.getvalue())


def write_library(path: Path = LIBRARY_FILE) -> bytes:
    """Render the library and write it to ``path`` (parent folders are created)."""
    data = render_library()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
