"""Build the symbol library DXF: one ``BLOCK`` per symbol and the ``Legend`` sheet (ADR-0005).

The file is ``symbols/pvsld-symbols-cfe.dxf`` (DXF R2018). It holds every block of
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
import math
import textwrap
from collections.abc import Iterable, Sequence
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
    Label,
    Line,
    Polyline,
    SymbolSpec,
)

LIBRARY_FILE = Path("symbols") / "pvsld-symbols-cfe.dxf"
LEGEND_LAYOUT = "Legend"
LEGEND_TITLE = "SIMBOLOGÍA — DIAGRAMAS UNIFILARES FV (CFE G0100-04 Apéndice C)"
LEGEND_COLUMNS = ("Símbolo", "Designación", "Fuente")
LEGEND_NOTES = (
    "Símbolos redibujados como geometría vectorial a partir de CFE G0100-04, Apéndices C y D "
    "(informativos); la especificación no se incluye ni se copia.",
    "Cada símbolo es un bloque PVSLD_<FUNCIÓN> con los atributos TAG y DESC y, ocultos, COMP_ID, "
    "IEC_REF, NMX_REF y SOURCE_STANDARD; los puertos están en XDATA (aplicación PVSLD).",
    "Dimensiones en mm a escala 1:1 dentro del bloque; en esta hoja cada símbolo se reduce, si "
    "hace falta, para caber en su celda.",
)
DOTTED = "DOTTED"
DASHDOT_SMALL = "DASHDOT_S"

SHEET_WIDTH_MM = 420.0
SHEET_HEIGHT_MM = 297.0
MARGIN_MM = 10.0
GROUP_GAP_MM = 10.0
COLUMN_WIDTHS_MM = (46.0, 82.0, 62.0)
TITLE_BAND_MM = 24.0
HEADER_ROW_MM = 8.0
FOOTER_MM = 22.0
MAX_ROW_MM = 21.0
CELL_PADDING_MM = 4.0
CHAR_WIDTH_FACTOR = 0.68
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


def legend_rows(count: int) -> tuple[int, float]:
    """Rows per column group and the row height for ``count`` symbols in two groups."""
    rows = math.ceil(count / 2)
    available = SHEET_HEIGHT_MM - 2 * MARGIN_MM - TITLE_BAND_MM - HEADER_ROW_MM - FOOTER_MM
    return rows, min(MAX_ROW_MM, available / rows)


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


def _build_legend(doc: Drawing, specs: Sequence[SymbolSpec]) -> BaseLayout:
    doc.layouts.rename("Layout1", LEGEND_LAYOUT)
    paper = doc.layouts.get(LEGEND_LAYOUT)
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

    frame, tables, notes = layers.TITLE_BLOCK, layers.TABLES, layers.NOTES
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
    top = SHEET_HEIGHT_MM - MARGIN_MM
    _text(paper, frame, MARGIN_MM + 5, top - 10, 6, LEGEND_TITLE)
    _text(
        paper,
        notes,
        MARGIN_MM + 5,
        top - 18,
        3.5,
        f"Biblioteca de símbolos pvsld v{LIBRARY_VERSION} — {len(specs)} bloques — DXF R2018",
    )

    rows, row_h = legend_rows(len(specs))
    table_top = top - TITLE_BAND_MM
    group_w = sum(COLUMN_WIDTHS_MM)
    for group in range(2):
        x0 = MARGIN_MM + 5 + group * (group_w + GROUP_GAP_MM)
        members = specs[group * rows : (group + 1) * rows]
        if not members:
            continue
        bottom = table_top - HEADER_ROW_MM - row_h * len(members)
        xs = [x0]
        for width in COLUMN_WIDTHS_MM:
            xs.append(xs[-1] + width)
        paper.add_lwpolyline(
            [(xs[0], table_top), (xs[-1], table_top), (xs[-1], bottom), (xs[0], bottom)],
            close=True,
            dxfattribs=_attribs(tables),
        )
        for x in xs[1:-1]:
            paper.add_line((x, table_top), (x, bottom), dxfattribs=_attribs(tables))
        for index in range(len(members) + 1):
            y = table_top - HEADER_ROW_MM - row_h * index
            paper.add_line((xs[0], y), (xs[-1], y), dxfattribs=_attribs(tables))
        for column, title in enumerate(LEGEND_COLUMNS):
            _text(paper, notes, xs[column] + 3, table_top - 5.5, 3.5, title)
        for index, spec in enumerate(members):
            row_top = table_top - HEADER_ROW_MM - row_h * index
            _legend_row(paper, spec, xs, row_top, row_h)

    y = MARGIN_MM + FOOTER_MM - 4
    for note in LEGEND_NOTES:
        for wrapped in _wrap(note, SHEET_WIDTH_MM - 2 * MARGIN_MM - 10, 2.5):
            _text(paper, notes, MARGIN_MM + 5, y, 2.5, wrapped)
            y -= 3.6
    return paper


def _legend_row(
    paper: BaseLayout, spec: SymbolSpec, xs: Sequence[float], row_top: float, row_h: float
) -> None:
    cell_w = COLUMN_WIDTHS_MM[0]
    scale, dx, dy = _fit(spec, cell_w, row_h)
    paper.add_blockref(
        spec.name,
        (round(xs[0] + dx, 4), round(row_top - row_h + dy, 4)),
        dxfattribs={
            "layer": layers.NOTES,
            "xscale": scale,
            "yscale": scale,
            "zscale": scale,
        },
    )
    designation = _wrap(spec.description_es, COLUMN_WIDTHS_MM[1] - 6, 3.2)
    y = row_top - 6.5
    for line in designation:
        _text(paper, layers.NOTES, xs[1] + 3, y, 3.2, line)
        y -= 4.6
    _text(paper, layers.NOTES, xs[1] + 3, y - 0.4, 2.2, spec.name)
    y = row_top - 6.5
    for line in _wrap(spec.source, COLUMN_WIDTHS_MM[2] - 6, 2.8):
        _text(paper, layers.NOTES, xs[2] + 3, y, 2.8, line)
        y -= 4.0


# --- Document and bytes ----------------------------------------------------------------------


def build_document(specs: Iterable[SymbolSpec] = LIBRARY) -> Drawing:
    """The library as an in-memory ezdxf document: every block and the ``Legend`` layout."""
    chosen = tuple(specs)
    doc = _new_document()
    doc.linetypes.add(DOTTED, pattern=[1.5, 0.0, -1.5], description="Dotted .  .  .  .")
    doc.linetypes.add(
        DASHDOT_SMALL, pattern=[8.0, 5.0, -1.5, 0.0, -1.5], description="Dash dot (small) _ . _ ."
    )
    for spec in chosen:
        define_block(doc, spec)
    _build_legend(doc, chosen)
    doc.layouts.set_active_layout(LEGEND_LAYOUT)
    doc.header["$LIMMIN"] = (0.0, 0.0)
    doc.header["$LIMMAX"] = (SHEET_WIDTH_MM, SHEET_HEIGHT_MM)
    doc.header["$EXTMIN"] = (MARGIN_MM, MARGIN_MM, 0.0)
    doc.header["$EXTMAX"] = (SHEET_WIDTH_MM - MARGIN_MM, SHEET_HEIGHT_MM - MARGIN_MM, 0.0)
    doc.header["$PROJECTNAME"] = "pvsld-symbols-cfe"
    doc.ezdxf_metadata()["PVSLD_LIBRARY_VERSION"] = LIBRARY_VERSION
    _sort_class_registration(doc)
    return doc


def render_library(specs: Iterable[SymbolSpec] = LIBRARY) -> bytes:
    """The bytes of ``pvsld-symbols-cfe.dxf``: UTF-8, LF newlines, identical on every platform."""
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
