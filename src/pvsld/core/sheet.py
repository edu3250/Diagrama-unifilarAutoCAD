"""Sheet templates: the owner's drawing sheet as data (frame, boxes, fixed texts and fields).

A :class:`SheetTemplate` is read from a DXF by :mod:`pvsld.sheets.loader`. Everything in it is
in sheet millimetres on the A3 paper and goes to paper space. ``fields`` are the texts that change
with every design: the template keeps their position, style, height, layer and alignment, and the
layout writes the value (:mod:`pvsld.core.layout_sheet`). Personal data fields stay blank lines to
be filled by hand.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace

from pvsld.core.diagram import CircleItem, LineItem, PolylineItem, TextItem


class SheetTemplateError(ValueError):
    """The template file does not match its definition; the message says what is missing."""


@dataclass(frozen=True)
class SheetTemplate:
    name: str
    texts: tuple[TextItem, ...]
    lines: tuple[LineItem, ...]
    polylines: tuple[PolylineItem, ...]
    circles: tuple[CircleItem, ...]
    fields: Mapping[str, TextItem]
    """Prototype of each field (its ``text`` is empty), by field name."""
    text_styles: tuple[tuple[str, str], ...]

    def field(self, name: str, text: str) -> TextItem:
        """The field ``name`` carrying ``text``."""
        try:
            prototype = self.fields[name]
        except KeyError:
            raise SheetTemplateError(f"template {self.name} has no field {name!r}") from None
        return replace(prototype, text=text)
