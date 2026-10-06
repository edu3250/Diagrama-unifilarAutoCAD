"""B1: the ezdxf backend. Materializes a :class:`Diagram` as a DXF R2018 (AC1032) file.

The file has an A3 paper-space layout (border, title block with attributes, revision block and a
1:1 viewport onto the model), the house layer standard, one ``BLOCK`` per used symbol with
``ATTDEF`` s and port data, and one ``INSERT`` with ``ATTRIB`` s per component. Identity and
connectivity are stored as data, so the file can be read back and checked (see
:mod:`pvsld.backends.readback`):

* block record XDATA, application ``PVSLD``: ``pvsld.block/1``, library version, ports;
* INSERT XDATA: ``pvsld.instance/1``, ``COMP_ID``;
* conductor LWPOLYLINE XDATA: ``pvsld.wire/1``, connection id, circuit id, start and end port.

Determinism. With ``deterministic=True`` (the default) ezdxf's fixed-metadata mode pins timestamps
and GUIDs, handles are sequential, and the text is encoded to UTF-8 bytes here with LF newlines on
every platform (ezdxf's own ``saveas`` would turn ``\\n`` into ``\\r\\n`` on Windows). The same
diagram therefore yields the same bytes on Windows and Linux. ``.gitattributes`` marks ``*.dxf``
as ``-text`` so a committed golden file keeps its bytes.
"""

from __future__ import annotations

import io
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import ezdxf
from ezdxf.document import Drawing
from ezdxf.layouts import BaseLayout
from ezdxf.lldxf import const

from pvsld.backends.base import RenderResult, sha256_hex
from pvsld.core import layers
from pvsld.core.diagram import Diagram, Table, rnd
from pvsld.symbols import APP_ID, get_symbol
from pvsld.symbols.catalogue import (
    SYMBOLS,
    Circle,
    Label,
    Line,
    Polyline,
    SymbolDef,
)

DXF_VERSION = "R2018"
LAYOUT_NAME = "A3"
TEXT_STYLE = "PVSLD_STD"
FONT = "arial.ttf"
MILLIMETRES = 4  # $INSUNITS value

BLOCK_FORMAT = "pvsld.block/1"
INSTANCE_FORMAT = "pvsld.instance/1"
WIRE_FORMAT = "pvsld.wire/1"

# Metric (ISO-like) patterns, in drawing units (mm): total length, then dash and gap lengths.
LINETYPES: dict[str, tuple[str, list[float]]] = {
    "DASHED": ("Dashed __ __ __ __ __ __", [18.0, 12.0, -6.0]),
    "DASHDOT": ("Dash dot __ . __ . __ .", [24.0, 12.0, -6.0, 0.0, -6.0]),
}


@contextmanager
def fixed_metadata(enabled: bool) -> Iterator[None]:
    """Pin ezdxf's timestamps and GUIDs for the duration of the block, then restore the option.

    The option is process-global in ezdxf, so deterministic renders must not run concurrently
    with non-deterministic ones in the same process.
    """
    previous = ezdxf.options.write_fixed_meta_data_for_testing
    ezdxf.options.write_fixed_meta_data_for_testing = enabled or previous
    try:
        yield
    finally:
        ezdxf.options.write_fixed_meta_data_for_testing = previous


def _attribs(layer: str, *, weight: int | None = None) -> dict[str, Any]:
    attribs: dict[str, Any] = {"layer": layer}
    if weight is not None:
        attribs["lineweight"] = weight
    return attribs


# --- Document set-up -----------------------------------------------------------------------------


def _new_document() -> Drawing:
    doc = ezdxf.new(DXF_VERSION, setup=False, units=MILLIMETRES)
    doc.header["$MEASUREMENT"] = 1
    doc.header["$LUNITS"] = 2
    doc.header["$LTSCALE"] = 1.0
    for name, (description, pattern) in LINETYPES.items():
        doc.linetypes.add(name, pattern=pattern, description=description)
    doc.styles.add(TEXT_STYLE, font=FONT)
    doc.header["$TEXTSTYLE"] = TEXT_STYLE
    doc.appids.add(APP_ID)
    for layer in layers.LAYERS:
        entry = doc.layers.add(
            layer.name, color=layer.aci, linetype=layer.linetype, lineweight=layer.lineweight
        )
        entry.description = layer.description_es
        if not layer.plot:
            entry.dxf.plot = 0
    return doc


def _port_xdata(symbol: SymbolDef) -> list[tuple[int, Any]]:
    tags: list[tuple[int, Any]] = [
        (1000, BLOCK_FORMAT),
        (1000, symbol.library_version),
        (1070, len(symbol.ports)),
    ]
    for port in symbol.ports:
        tags += [
            (1000, port.id),
            (1000, port.kind),
            (1000, port.direction),
            (1040, float(port.x)),
            (1040, float(port.y)),
            (1070, int(port.required)),
        ]
    return tags


def define_symbol_block(doc: Drawing, symbol: SymbolDef) -> None:
    """Add the ``BLOCK`` of ``symbol``: geometry, attribute definitions and port XDATA."""
    block = doc.blocks.new(symbol.name, base_point=(0, 0))
    for item in symbol.geometry:
        if isinstance(item, Line):
            block.add_line(
                (item.x1, item.y1),
                (item.x2, item.y2),
                dxfattribs=_attribs(item.layer, weight=item.lineweight),
            )
        elif isinstance(item, Polyline):
            block.add_lwpolyline(
                list(item.points), close=item.closed, dxfattribs=_attribs(item.layer)
            )
        elif isinstance(item, Circle):
            block.add_circle((item.cx, item.cy), item.radius, dxfattribs=_attribs(item.layer))
        elif isinstance(item, Label):
            text = block.add_text(
                item.text,
                height=item.height,
                dxfattribs={"layer": item.layer, "style": TEXT_STYLE},
            )
            text.set_placement((item.x, item.y))
    for attdef in symbol.attdefs:
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
    block.block_record.set_xdata(APP_ID, _port_xdata(symbol))


def _sort_class_registration(doc: Drawing) -> None:
    """Make the order of the CLASSES section independent of ``PYTHONHASHSEED``.

    ezdxf 1.4.4 registers the CLASS record of every entity type in use by iterating a ``set`` of
    type names (``ClassesSection.add_required_classes``), so the section order, and with it the
    file bytes, changes from one process to the next. Handing it a sorted list instead fixes that.
    The override lives on this document's entity database only; nothing global is patched.
    """
    database = doc.entitydb

    def types_in_use() -> list[str]:
        return sorted({entity.dxftype() for entity in database.values()})

    database.dxf_types_in_use = types_in_use  # type: ignore[method-assign]


# --- Drawing the diagram -------------------------------------------------------------------------


def _draw_table(target: BaseLayout, table: Table) -> None:
    for line in table.lines():
        target.add_line(
            (line.x1, line.y1), (line.x2, line.y2), dxfattribs=_attribs(line.layer, weight=None)
        )
    for text in table.texts():
        _add_text(target, text.layer, text.x, text.y, text.height, text.text)


def _add_text(target: BaseLayout, layer: str, x: float, y: float, height: float, text: str) -> None:
    target.add_text(
        text, height=height, dxfattribs={"layer": layer, "style": TEXT_STYLE}
    ).set_placement((x, y))


def _build_document(diagram: Diagram) -> Drawing:
    doc = _new_document()
    used = {item.symbol for item in diagram.instances}
    for name, symbol in SYMBOLS.items():
        if name in used:
            define_symbol_block(doc, symbol)

    model = doc.modelspace()
    doc.layouts.rename("Layout1", LAYOUT_NAME)
    paper = doc.layouts.get(LAYOUT_NAME)
    border = diagram.sheet.border
    paper.page_setup(
        size=(diagram.sheet.width, diagram.sheet.height),
        margins=(0, 0, 0, 0),
        units="mm",
        offset=(0, 0),
        rotation=0,
        scale=16,
        name=f"ISO_{diagram.sheet.name}_({diagram.sheet.width:.2f}_x_{diagram.sheet.height:.2f}_MM)",
        device="DWG to PDF.pc3",
    )
    # page_setup() makes ezdxf add the paper-space main viewport on a layer of its own; keep every
    # entity on the house layers (the viewport frame must not plot).
    main_viewport = paper.main_viewport()
    if main_viewport is not None:
        main_viewport.dxf.layer = diagram.viewport.layer
    spaces: dict[str, BaseLayout] = {"model": model, "paper": paper}

    for item in diagram.instances:
        symbol = get_symbol(item.symbol)
        target = spaces[item.space]
        ref = target.add_blockref(item.symbol, (item.x, item.y), dxfattribs={"layer": item.layer})
        values = item.values
        for attdef in symbol.attdefs:
            attribs: dict[str, Any] = {
                "layer": attdef.layer,
                "style": TEXT_STYLE,
                "height": attdef.height,
            }
            if not attdef.visible:
                attribs["flags"] = const.ATTRIB_INVISIBLE
            ref.add_attrib(
                attdef.tag,
                values[attdef.tag],
                insert=(rnd(item.x + attdef.x), rnd(item.y + attdef.y)),
                dxfattribs=attribs,
            )
        ref.set_xdata(APP_ID, [(1000, INSTANCE_FORMAT), (1000, item.comp_id)])

    for conn in diagram.connections:
        wire = model.add_lwpolyline(
            [(p.x, p.y) for p in conn.points], dxfattribs=_attribs(conn.layer)
        )
        wire.set_xdata(
            APP_ID,
            [
                (1000, WIRE_FORMAT),
                (1000, conn.id),
                (1000, conn.circuit_id or ""),
                (1000, conn.kind),
                (1000, str(conn.start)),
                (1000, str(conn.end)),
            ],
        )

    for text in diagram.texts:
        _add_text(spaces[text.space], text.layer, text.x, text.y, text.height, text.text)
    for line in diagram.lines:
        spaces[line.space].add_line(
            (line.x1, line.y1),
            (line.x2, line.y2),
            dxfattribs=_attribs(line.layer, weight=line.lineweight),
        )
    for poly in diagram.polylines:
        spaces[poly.space].add_lwpolyline(
            [(p.x, p.y) for p in poly.points], close=poly.closed, dxfattribs=_attribs(poly.layer)
        )
    for table in diagram.tables:
        _draw_table(spaces[table.space], table)

    vp = diagram.viewport
    paper.add_viewport(
        center=(vp.center.x, vp.center.y),
        size=vp.size,
        view_center_point=(vp.view_center.x, vp.view_center.y),
        view_height=vp.view_height,
        status=1,
        dxfattribs={"layer": vp.layer},
    )

    # The file opens on the A3 sheet, framed on the border.
    doc.layouts.set_active_layout(LAYOUT_NAME)
    doc.set_modelspace_vport(height=vp.view_height, center=(vp.view_center.x, vp.view_center.y))
    doc.header["$LIMMIN"] = (0.0, 0.0)
    doc.header["$LIMMAX"] = (diagram.sheet.width, diagram.sheet.height)
    doc.header["$EXTMIN"] = (border.x0, border.y0, 0.0)
    doc.header["$EXTMAX"] = (border.x1, border.y1, 0.0)
    metadata = dict(diagram.metadata)
    doc.header["$PROJECTNAME"] = metadata.get("PROJECT_ID", "")
    custom = doc.ezdxf_metadata()
    for key, value in diagram.metadata:
        custom[f"PVSLD_{key}"] = value
    _sort_class_registration(doc)
    return doc


# --- Public API ----------------------------------------------------------------------------------


@dataclass(frozen=True)
class DxfOutput:
    """A rendered drawing: the in-memory ezdxf document and the exact bytes of the DXF file."""

    document: Drawing
    data: bytes

    @property
    def sha256(self) -> str:
        return sha256_hex(self.data)


def render_dxf(diagram: Diagram, *, deterministic: bool = True) -> DxfOutput:
    """Build the DXF for ``diagram`` in memory.

    With ``deterministic=True`` the bytes depend only on the diagram (and the ezdxf version), not
    on the clock, the machine or the operating system.
    """
    with fixed_metadata(deterministic):
        doc = _build_document(diagram)
        stream = io.StringIO()
        doc.write(stream)
        data = doc.encode(stream.getvalue())
    return DxfOutput(document=doc, data=data)


def write_dxf(diagram: Diagram, path: Path, *, deterministic: bool = True) -> DxfOutput:
    """Render ``diagram`` and write the bytes to ``path`` (parent folders are created)."""
    output = render_dxf(diagram, deterministic=deterministic)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(output.data)
    return output


def render_symbol_library(*, deterministic: bool = True) -> bytes:
    """A DXF that holds every block of the symbol library and no drawing entities.

    Both backends insert these definitions (ADR-0001, point 6), and CAD users can load them as a
    master library.
    """
    with fixed_metadata(deterministic):
        doc = _new_document()
        for symbol in SYMBOLS.values():
            define_symbol_block(doc, symbol)
        _sort_class_registration(doc)
        stream = io.StringIO()
        doc.write(stream)
        return doc.encode(stream.getvalue())


class DxfBackend:
    """``RenderBackend`` implementation of B1."""

    name = "ezdxf"

    def __init__(self, *, deterministic: bool = True) -> None:
        self.deterministic = deterministic

    def render(self, diagram: Diagram, output: Path) -> RenderResult:
        rendered = write_dxf(diagram, output, deterministic=self.deterministic)
        return RenderResult(
            backend=self.name,
            path=output,
            size_bytes=len(rendered.data),
            sha256=rendered.sha256,
        )
