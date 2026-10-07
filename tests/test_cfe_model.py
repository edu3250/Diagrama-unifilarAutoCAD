"""Geometry helpers of the symbol model: bounds and the distance of a port to the drawing."""

from __future__ import annotations

import pytest

from pvsld.symbols.cfe.model import (
    Arc,
    Circle,
    Dot,
    Label,
    Line,
    Polyline,
    SymbolSpec,
    distance_to_outline,
)

L = "E-PVAC-EQPM"


def test_distance_to_a_line_and_a_closed_polyline() -> None:
    assert distance_to_outline(Line(0, 0, 10, 0, L), 5, 3) == pytest.approx(3)
    assert distance_to_outline(Line(0, 0, 10, 0, L), 13, 4) == pytest.approx(5)  # beyond the end
    assert distance_to_outline(Line(2, 2, 2, 2, L), 5, 6) == pytest.approx(5)  # degenerate
    square = Polyline(((0, 0), (4, 0), (4, 4), (0, 4)), L, closed=True)
    assert distance_to_outline(square, 0, 2) == pytest.approx(0)  # on the closing edge
    open_square = Polyline(((0, 0), (4, 0), (4, 4), (0, 4)), L)
    assert distance_to_outline(open_square, 0, 2) == pytest.approx(2)


def test_distance_to_a_circle_an_arc_a_dot_and_a_label() -> None:
    assert distance_to_outline(Circle(0, 0, 5, L), 5, 0) == pytest.approx(0)
    assert distance_to_outline(Circle(0, 0, 5, L), 0, 2) == pytest.approx(3)
    arc = Arc(0, 0, 5, 0, 90, L)
    assert distance_to_outline(arc, 5, 0) == pytest.approx(0, abs=1e-6)
    assert distance_to_outline(arc, -5, 0) > 5  # the other half of the circle is not the arc
    assert distance_to_outline(Dot(0, 0, 1, L), 0.5, 0) == 0
    assert distance_to_outline(Dot(0, 0, 1, L), 3, 0) == pytest.approx(2)
    assert distance_to_outline(Label(0, 0, 2.5, "kWh"), 0, 0) == float("inf")


def test_an_arc_that_wraps_through_zero_degrees_is_followed() -> None:
    arc = Arc(0, 0, 5, 300, 60, L)
    assert distance_to_outline(arc, 5, 0) == pytest.approx(0, abs=1e-6)


def test_bounds_cover_lines_circles_arcs_dots_and_labels() -> None:
    spec = SymbolSpec(
        name="PVSLD_X",
        description_es="x",
        source="pvsld",
        iec_ref="-",
        nmx_ref="-",
        layer=L,
        geometry=(
            Line(0, 0, 4, 0, L),
            Circle(10, 0, 2, L),
            Arc(0, -10, 2, 0, 180, L),
            Dot(-5, 0, 1, L),
            Label(0, 5, 2, "ab"),
        ),
        attdefs=(),
        ports=(),
    )
    x0, y0, x1, y1 = spec.bounds()
    assert x0 == pytest.approx(-6)
    assert x1 == pytest.approx(12)
    assert y0 == pytest.approx(-10)
    assert y1 == pytest.approx(7)
    with pytest.raises(KeyError, match="no port"):
        spec.port("NOPE")
