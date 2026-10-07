"""Sized specifications with real catalogue names must produce a drawing that passes read-back."""

from __future__ import annotations

import json
import re
from pathlib import Path

import ezdxf
import pytest

from pvsld.core.layout import LayoutError, _wrap_rows
from pvsld.service import generate_single_line_diagram
from sizing_helpers import (
    ET_550,
    GROWATT_5K,
    HUAWEI_5K,
    JINKO_650,
    registry,
    size,
)

# Two string breakers add rows to the protection table: with the long Jinko names the lower-left
# band (130 mm tall) is then full, a sheet capacity limit unrelated to the table widths.
SCENARIOS = [
    pytest.param(JINKO_650, GROWATT_5K, {}, id="jinko-growatt"),
    pytest.param(ET_550, GROWATT_5K, {}, id="etsolar-growatt"),
    pytest.param(ET_550, HUAWEI_5K, {}, id="etsolar-huawei"),
]


@pytest.mark.parametrize(("module", "inverter", "fields"), SCENARIOS)
def test_selected_spec_generates_a_verified_diagram(
    tmp_path: Path, module: str, inverter: str, fields: dict[str, str]
) -> None:
    result = size(module, [inverter], target_dc_power_w=9000, **fields)
    assert result.spec is not None
    generated = generate_single_line_diagram(result.spec, tmp_path / "sld.dxf")
    assert generated.validation.ok
    assert generated.readback is not None
    assert generated.readback.problems == ()
    assert generated.readback.audit_errors == 0
    assert generated.ok


def test_every_candidate_of_a_real_catalogue_scenario_is_drawable(tmp_path: Path) -> None:
    result = size(JINKO_650, [GROWATT_5K], target_dc_power_w=9000)
    assert len(result.candidates) > 1
    for candidate in result.candidates:
        generated = generate_single_line_diagram(candidate.spec, tmp_path / "c.dxf")
        assert generated.ok, candidate.config.label


def test_long_cells_wrap_onto_continuation_rows() -> None:
    header = ("Equipo", "Datos")
    rows = (
        ("Módulo", "100 W; Voc 49.60 V; Isc 14.00 A; Vmp 41.60 V; Imp 13.22 A; β Voc -0.27 %/°C"),
    )
    wrapped = _wrap_rows("TBL-X", "TÍTULO", header, rows, max_width=60)
    assert len(wrapped) > 1
    assert wrapped[0][0] == "Módulo"
    assert all(row[0] == "" for row in wrapped[1:])
    assert " ".join(row[1] for row in wrapped).replace("; ", ";").count("Imp 13.22 A") == 1


def test_a_table_that_fits_is_returned_unchanged() -> None:
    rows = (("Módulo", "corto"),)
    assert _wrap_rows("TBL-X", "T", ("A", "B"), rows, max_width=200) is rows


def test_an_unbreakable_word_that_cannot_fit_names_the_cell() -> None:
    rows = (("Módulo", "X" * 80),)
    with pytest.raises(LayoutError, match=r"TBL-X.*'Datos'"):
        _wrap_rows("TBL-X", "T", ("Equipo", "Datos"), rows, max_width=40)


# --- The size quoted anywhere must be the designed one ------------------------------------------

_SIZE = re.compile(r"(\d+(?:\.\d+)?)\s*(kWp|kWac)")


def _dxf_texts(path: Path) -> list[str]:
    document = ezdxf.readfile(path)
    texts: list[str] = []
    for layout in document.layouts:
        for entity in layout:
            kind = entity.dxftype()
            if kind == "TEXT":
                texts.append(entity.dxf.text)
            elif kind == "MTEXT":
                texts.append(entity.text)
            elif kind == "INSERT":
                texts += [attrib.dxf.text for attrib in entity.attribs]
    return texts


@pytest.mark.parametrize(("module", "inverter"), [(ET_550, GROWATT_5K), (JINKO_650, GROWATT_5K)])
def test_every_size_in_the_spec_and_the_drawing_is_the_designed_one(
    tmp_path: Path, module: str, inverter: str
) -> None:
    result = size(module, [inverter], target_dc_power_w=9000)
    selected = result.selected
    assert selected is not None
    kwp = f"{selected.metrics.p_dc_w / 1000:.2f}"
    kwac = f"{registry().get(inverter).rated_ac_power_w / 1000:.2f}"  # type: ignore[union-attr]
    assert kwp != "7.70"  # the template's own size must not survive by coincidence

    spec_text = json.dumps(selected.spec, default=str, ensure_ascii=False)
    quoted = {(m.group(1), m.group(2)) for m in _SIZE.finditer(spec_text)}
    assert quoted <= {(kwp, "kWp"), (kwac, "kWac")}
    assert "7.70" not in spec_text
    assert selected.spec["project"]["name"].endswith(f"{kwp} kWp")

    generated = generate_single_line_diagram(selected.spec, tmp_path / "sld.dxf")
    assert generated.ok
    texts = _dxf_texts(tmp_path / "sld.dxf")
    found = {(m.group(1), m.group(2)) for text in texts for m in _SIZE.finditer(text)}
    assert (kwp, "kWp") in found
    assert found <= {(kwp, "kWp"), (kwac, "kWac")} | {
        (f"{n * selected.config.n_series * registry().get(module).pmax_w / 1000:.2f}", "kWp")  # type: ignore[union-attr]
        for n in (1, 2)
    }
    assert any(f"{kwp} kWp / {kwac} kWac" in text for text in texts)
    assert not any("7.70" in text for text in texts)
