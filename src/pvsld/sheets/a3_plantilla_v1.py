"""Definition of the owner's A3 sheet ``a3_plantilla_v1`` (layout template of the same name).

The sheet (frame 10-410 x 10-287 mm) has the schematic area in the middle, a right column
(macrolocation, location, address, installer, owner, system capacity) and a lower band (calculation
summary, abbreviations and notes, two circuit boxes, module and inverter data, symbology, title
block). A field is identified by the anchor of its text in the template: the left end of the
baseline, or the middle of a centred text. :mod:`pvsld.sheets.loader` keeps every other text,
line, polyline and circle as fixed sheet furniture, except what lies inside ``CLEARED``.
"""

from __future__ import annotations

from pvsld.core import layers

NAME = "a3_plantilla_v1"

SCHEMATIC_AREA = (14.0, 100.0, 311.0, 268.0)
"""``(x0, y0, x1, y1)`` free for the schematic, between the heading, the right column and the
lower band."""

CLEARED: tuple[tuple[float, float, float, float], ...] = ((139.0, 12.5, 237.5, 58.5),)
"""Regions whose content is redrawn per design (the symbology box holds the blocks drawn)."""
SYMBOLOGY_BOX = CLEARED[0]

LAYER_MAP: dict[str, str] = {
    "0": layers.NOTES,
    "MARCO": layers.TITLE_BLOCK,
    "TABLAS": layers.TABLES,
    "TEXTO": layers.NOTES,
    "EQUIPOS": layers.LABELS,
    "CIRCUITOS": layers.LABELS,
    "TIERRA": layers.LABELS,
    "GABINETES": layers.ENCLOSURES,
    "CALLOUT": layers.TAGS,
}
"""Template layer -> house layer (ADR-0003); the template's lineweights are kept per entity."""


def _column(prefix: str, x: float, ys: tuple[float, ...]) -> dict[str, tuple[float, float]]:
    return {f"{prefix}.{index}": (x, y) for index, y in enumerate(ys, start=1)}


_ROWS_9 = (55.0, 50.6, 46.2, 41.8, 37.4, 33.0, 28.6, 24.2, 19.8)

FIELDS: dict[str, tuple[float, float]] = {
    # heading
    "title": (158.0, 278.0),
    "subtitle": (158.0, 272.5),
    # right column
    "location.lat": (338.0, 212.0),
    "location.lon": (338.0, 208.6),
    "location.datum": (338.0, 205.2),
    "location.altitude": (338.0, 201.8),
    **_column("address", 316.0, (188.0, 184.6, 181.2, 177.8)),
    "installer.name": (334.0, 165.0),
    "installer.email": (334.0, 161.6),
    "installer.contact": (334.0, 158.2),
    "installer.cedula": (334.0, 154.8),
    "owner.name": (334.0, 140.0),
    "owner.rpu": (334.0, 136.6),
    "owner.service": (334.0, 133.2),
    "capacity.pdc": (338.0, 122.0),
    "capacity.pac": (338.0, 118.6),
    "capacity.ratio": (338.0, 115.2),
    "capacity.energy": (338.0, 111.8),
    # lower band
    **_column("memory", 14.0, (88.0, 84.8, 81.6, 78.4, 75.2, 72.0, 68.8)),
    **_column("notes", 140.0, (76.4, 73.5, 70.6, 67.7)),
    "circuit1.title": (254.0, 87.5),
    "circuit1.subtitle": (254.0, 84.5),
    **_column("circuit1", 244.0, (80.0, 77.3, 74.6, 71.9, 69.2)),
    "circuit2.title": (339.0, 87.5),
    "circuit2.subtitle": (339.0, 84.5),
    **_column("circuit2", 329.0, (80.0, 77.3, 74.6, 71.9, 69.2)),
    **_column("module", 30.0, _ROWS_9),
    **_column("inverter", 91.0, _ROWS_9),
    "symbology.title": (188.0, 61.5),
    # title block
    "company.name": (325.0, 59.0),
    "company.city": (325.0, 53.5),
    "project": (325.0, 46.0),
    "design.name": (266.0, 38.2),
    "design.cedula": (375.0, 38.2),
    "review.name": (266.0, 31.7),
    "review.cedula": (375.0, 31.7),
    "owner.title_name": (266.0, 25.2),
    "owner.contact": (375.0, 25.2),
    "drawing": (266.0, 18.7),
    "date": (375.0, 18.7),
}

FONT_MAP: dict[str, str] = {
    "OpenSans-Regular.ttf": "arial.ttf",
    "OpenSansCondensed-Bold.ttf": "ARIALNB.TTF",
}
"""Fonts of the template replaced by fonts every Windows has: Open Sans is not installed with
AutoCAD, which then falls back to ``simplex.shx`` (wider, no em dash) and lines overflow their
boxes. Arial's metrics are those :func:`pvsld.core.diagram.text_width_mm` measures with."""

MARKER_RADIUS_MM = 3.2
"""Circuit marker circle of the template (the numbered circles of the circuit boxes)."""
MARKER_TEXT = (3.0, "OpenSansCondensed-Bold")
"""Height and style of the number inside a circuit marker."""
