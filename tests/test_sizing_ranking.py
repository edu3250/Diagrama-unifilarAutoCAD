"""Stage 3.6.0: rank by a DC/AC ratio near 1.10-1.25 and explain the choice (owner 2026-10-09)."""

from __future__ import annotations

import pytest

from pvsld.sizing.engine import DC_AC_PREFERRED, dc_ac_gap
from sizing_helpers import ET_550, size


@pytest.mark.parametrize(
    ("ratio", "gap"), [(1.10, 0), (1.2, 0), (1.25, 0), (0.95, 0.15), (1.4, 0.15)]
)
def test_the_gap_is_zero_inside_the_preferred_band(ratio: float, gap: float) -> None:
    assert DC_AC_PREFERRED == (1.10, 1.25)
    assert dc_ac_gap(ratio) == pytest.approx(gap)


def test_a_fixed_module_count_takes_the_inverter_closest_to_the_band() -> None:
    result = size(ET_550, "auto", module_count_min=5, module_count_max=5)
    selected = result.selected
    assert selected is not None
    others = [c.metrics.dc_ac_ratio for c in result.candidates[1:]]
    assert all(dc_ac_gap(selected.metrics.dc_ac_ratio) <= dc_ac_gap(r) for r in others)
    assert selected.explanation_es.startswith("Se eligió el inversor")
    assert f"{selected.metrics.dc_ac_ratio:.2f}" in selected.explanation_es
    assert "1.10 a 1.25" in selected.explanation_es


def test_one_string_uses_the_four_poles_of_the_box_switch() -> None:
    result = size(ET_550, "auto", module_count_min=5, module_count_max=5)
    assert result.selected is not None
    box = next(d for d in result.spec["dc_bos"]["disconnects"] if d["id"] == "DCD-CD1")  # type: ignore[index]
    assert box["poles"] == 4
