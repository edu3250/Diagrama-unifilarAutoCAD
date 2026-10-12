"""Read a sheet template DXF into a :class:`~pvsld.core.sheet.SheetTemplate`.

The template is drawn in model space at 1:1 on the A3 sheet (millimetres). Texts whose anchor
is a field of the definition become fields; empty texts and anything inside a cleared region are
dropped; the rest (lines, polylines, circles, texts) is fixed furniture, moved to the house layers
of the definition's layer map with the template layer's lineweight kept on each entity.

:func:`write_template` saves a template back as a neutral DXF: house layers, the fields as
``{name}`` placeholders, no other text of the source file and no drawing metadata (author,
dates). ``pvsld sheet import`` does both, converting a DWG with the Core Console first.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from types import ModuleType
from typing import Any

import ezdxf
from ezdxf.document import Drawing
from ezdxf.enums import TextEntityAlignment

from pvsld.core import layers
from pvsld.core.diagram import CircleItem, LineItem, Point, PolylineItem, TextItem, rnd
from pvsld.core.sheet import SheetTemplate, SheetTemplateError
from pvsld.resources import data_path
from pvsld.sheets import a3_plantilla_v1

ENV_SHEET_TEMPLATE = "PVSLD_SHEET_TEMPLATE"
"""Path of the template DXF; default ``sheet_templates/<name>.dxf``, packaged or in the
repository (:func:`pvsld.resources.data_path`)."""
ANCHOR_TOLERANCE_MM = 0.05
DEFINITIONS: dict[str, ModuleType] = {a3_plantilla_v1.NAME: a3_plantilla_v1}


def template_path(name: str) -> Path:
    configured = os.environ.get(ENV_SHEET_TEMPLATE)
    return Path(configured) if configured else data_path(f"sheet_templates/{name}.dxf")


def _inside(points: list[tuple[float, float]], regions: Any) -> bool:
    return any(
        all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in points) for x0, y0, x1, y1 in regions
    )


def _lineweight(entity: Any, doc: Drawing) -> int | None:
    weight = entity.dxf.get("lineweight", -1)
    if weight < 0:  # BYLAYER (or BYBLOCK): keep the template layer's weight on the entity
        layer = doc.layers.get(entity.dxf.layer)
        weight = layer.dxf.get("lineweight", -3) if layer is not None else -3
    return weight if weight >= 0 else None


def read_template(doc: Drawing, definition: ModuleType = a3_plantilla_v1) -> SheetTemplate:
    """Split the model space of ``doc`` into fields and fixed furniture.

    Raises:
        SheetTemplateError: a field of the definition has no text in the template, a layer has
            no mapping, or the template holds an entity type this reader does not support.
    """
    layer_map: dict[str, str] = definition.LAYER_MAP
    anchors = {name: (x, y) for name, (x, y) in definition.FIELDS.items()}
    fields: dict[str, TextItem] = {}
    texts: list[TextItem] = []
    lines: list[LineItem] = []
    polylines: list[PolylineItem] = []
    circles: list[CircleItem] = []
    used_styles: set[str] = set()

    def house_layer(entity: Any) -> str:
        if entity.dxf.layer in layers.LAYER_NAMES:  # a neutral template written by this module
            return str(entity.dxf.layer)
        try:
            return layer_map[entity.dxf.layer]
        except KeyError:
            raise SheetTemplateError(
                f"template layer {entity.dxf.layer!r} has no house layer in {definition.NAME}"
            ) from None

    for entity in doc.modelspace():
        kind = entity.dxftype()
        if kind == "TEXT":
            centred = entity.dxf.get("halign", 0) != 0
            anchor = entity.dxf.align_point if centred else entity.dxf.insert
            x, y = rnd(anchor.x), rnd(anchor.y)
            style = entity.dxf.get("style", "Standard")
            item = TextItem(
                house_layer(entity),
                x,
                y,
                rnd(entity.dxf.height),
                entity.dxf.text,
                "paper",
                style=style,
                align="center" if centred else "left",
            )
            name = next(
                (
                    n
                    for n, (ax, ay) in anchors.items()
                    if abs(ax - x) <= ANCHOR_TOLERANCE_MM and abs(ay - y) <= ANCHOR_TOLERANCE_MM
                ),
                None,
            )
            if name is not None:
                fields[name] = TextItem(**{**item.__dict__, "text": ""})
                used_styles.add(style)
            elif item.text.strip() and not _inside([(x, y)], definition.CLEARED):
                texts.append(item)
                used_styles.add(style)
        elif kind == "LINE":
            points = [
                (entity.dxf.start.x, entity.dxf.start.y),
                (entity.dxf.end.x, entity.dxf.end.y),
            ]
            if not _inside(points, definition.CLEARED):
                (x1, y1), (x2, y2) = points
                lines.append(
                    LineItem(
                        house_layer(entity),
                        rnd(x1),
                        rnd(y1),
                        rnd(x2),
                        rnd(y2),
                        "paper",
                        _lineweight(entity, doc),
                    )
                )
        elif kind == "LWPOLYLINE":
            points = [(p[0], p[1]) for p in entity.get_points("xy")]
            if not _inside(points, definition.CLEARED):
                polylines.append(
                    PolylineItem(
                        house_layer(entity),
                        tuple(Point(rnd(x), rnd(y)) for x, y in points),
                        bool(entity.closed),
                        "paper",
                        _lineweight(entity, doc),
                    )
                )
        elif kind == "CIRCLE":
            center = entity.dxf.center
            r = entity.dxf.radius
            box = [(center.x - r, center.y - r), (center.x + r, center.y + r)]
            if not _inside(box, definition.CLEARED):
                circles.append(
                    CircleItem(house_layer(entity), rnd(center.x), rnd(center.y), rnd(r), "paper")
                )
        else:
            raise SheetTemplateError(
                f"template {definition.NAME}: unsupported {kind} on layer {entity.dxf.layer}"
            )

    missing = sorted(set(anchors) - set(fields))
    if missing:
        raise SheetTemplateError(
            f"template does not match {definition.NAME}; no text at the anchor of "
            f"{', '.join(missing)}"
        )
    used_styles.add(definition.MARKER_TEXT[1])
    font_map: dict[str, str] = getattr(definition, "FONT_MAP", {})
    styles = tuple(
        sorted(
            (style.dxf.name, font_map.get(style.dxf.font, style.dxf.font))
            for style in doc.styles
            if style.dxf.name in used_styles and style.dxf.font
        )
    )
    return SheetTemplate(
        name=definition.NAME,
        texts=tuple(texts),
        lines=tuple(lines),
        polylines=tuple(polylines),
        circles=tuple(circles),
        fields=fields,
        text_styles=styles,
    )


def load_sheet_template(name: str, path: Path | None = None) -> SheetTemplate:
    """Read the template ``name`` from ``path`` (default :func:`template_path`).

    Raises:
        SheetTemplateError: unknown template name, missing file, or a file that does not match.
    """
    try:
        definition = DEFINITIONS[name]
    except KeyError:
        raise SheetTemplateError(f"unknown sheet template {name!r}") from None
    source = path or template_path(name)
    if not source.is_file():
        raise SheetTemplateError(
            f"sheet template file {source} not found; set ${ENV_SHEET_TEMPLATE} or save the "
            f"template as DXF there"
        )
    return read_template(ezdxf.readfile(source), definition)


def write_template(template: SheetTemplate, path: Path) -> bytes:
    """Save ``template`` as a neutral DXF R2018 (model space, sheet millimetres) and return it.

    Every field is a ``{name}`` placeholder text; the bytes depend only on the template.
    """
    from pvsld.backends.dxf import _new_document, _sort_class_registration, fixed_metadata

    with fixed_metadata(True):
        doc = _new_document()
        for name, font in template.text_styles:
            if name not in doc.styles:
                doc.styles.add(name, font=font)
        msp = doc.modelspace()
        for line in template.lines:
            attribs: dict[str, Any] = {"layer": line.layer}
            if line.lineweight is not None:
                attribs["lineweight"] = line.lineweight
            msp.add_line((line.x1, line.y1), (line.x2, line.y2), dxfattribs=attribs)
        for poly in template.polylines:
            attribs = {"layer": poly.layer}
            if poly.lineweight is not None:
                attribs["lineweight"] = poly.lineweight
            msp.add_lwpolyline(
                [(p.x, p.y) for p in poly.points], close=poly.closed, dxfattribs=attribs
            )
        for circle in template.circles:
            msp.add_circle(
                (circle.cx, circle.cy), circle.radius, dxfattribs={"layer": circle.layer}
            )
        placeholders = [
            TextItem(**{**item.__dict__, "text": f"{{{name}}}"})
            for name, item in sorted(template.fields.items())
        ]
        for text in (*template.texts, *placeholders):
            entity = msp.add_text(
                text.text,
                height=text.height,
                dxfattribs={"layer": text.layer, "style": text.style or "Standard"},
            )
            if text.align == "center":
                entity.set_placement((text.x, text.y), align=TextEntityAlignment.MIDDLE_CENTER)
            else:
                entity.set_placement((text.x, text.y))
        doc.header["$PROJECTNAME"] = template.name
        _sort_class_registration(doc)
        stream = io.StringIO()
        doc.write(stream)
        data = doc.encode(stream.getvalue())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
