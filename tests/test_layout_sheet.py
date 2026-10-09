"""Layout template ``a3_plantilla_v1``: the schematic on the owner's sheet template.

The owner's template is not in the repository, so these tests build a synthetic template with
the same field anchors (a text at every anchor, the frame boxes, something inside the cleared
symbology box) and check the reader, the neutral writer, the layout and the rendered file.
"""

from __future__ import annotations

import re
from itertools import combinations
from pathlib import Path
from typing import Any

import ezdxf
import pytest
from ezdxf.enums import TextEntityAlignment

from pvsld.backends.dxf import render_dxf
from pvsld.backends.readback import verify
from pvsld.cli import main
from pvsld.core.diagram import Box, Diagram, check_diagram
from pvsld.core.layout import LayoutError
from pvsld.core.layout_sheet import COMPANY, build_sheet_diagram
from pvsld.core.sheet import SheetTemplate, SheetTemplateError
from pvsld.core.validation import validate_pv_design
from pvsld.service import layout_diagram
from pvsld.sheets import a3_plantilla_v1 as definition
from pvsld.sheets.importer import dwg_to_dxf, dxfout_script, import_template
from pvsld.sheets.loader import (
    ENV_SHEET_TEMPLATE,
    load_sheet_template,
    read_template,
    write_template,
)
from pvsld.symbols import get_symbol
from s1_helpers import mutated
from test_core_diagram import MIN_GAP_MM, _model_boxes, _segment_hits

CENTRED = {"title", "subtitle", "symbology.title", "company.name", "company.city", "project"}
SECRET = "Dato Personal Del Dueño"


def _template_doc(*, skip: str | None = None, extra: str | None = None) -> ezdxf.document.Drawing:
    doc = ezdxf.new("R2018", setup=False, units=4)
    doc.styles.add("OpenSans", font="OpenSans-Regular.ttf")
    doc.styles.add("OpenSansCondensed-Bold", font="OpenSansCondensed-Bold.ttf")
    for name in definition.LAYER_MAP:
        if name not in doc.layers:
            doc.layers.add(name, lineweight=50 if name == "MARCO" else 18)
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(10, 10), (410, 10), (410, 287), (10, 287)], close=True, dxfattribs={"layer": "MARCO"}
    )
    msp.add_lwpolyline(
        [(313, 100), (408, 100), (408, 283), (313, 283)], close=True, dxfattribs={"layer": "TABLAS"}
    )
    msp.add_lwpolyline(
        [(12, 12), (238, 12), (238, 95), (12, 95)], close=True, dxfattribs={"layer": "TABLAS"}
    )
    msp.add_lwpolyline(
        [(138, 12), (238, 12), (238, 64), (138, 64)], close=True, dxfattribs={"layer": "TABLAS"}
    )
    msp.add_line((142, 40), (150, 48), dxfattribs={"layer": "EQUIPOS"})  # inside the cleared box
    msp.add_circle((248, 85), 3.2, dxfattribs={"layer": "CALLOUT"})
    msp.add_text(
        "LATITUD:", height=1.6, dxfattribs={"layer": "TEXTO", "style": "OpenSans"}
    ).set_placement((316, 212))
    msp.add_text("", height=1.5, dxfattribs={"layer": "TEXTO"}).set_placement((178, 257))
    for name, (x, y) in definition.FIELDS.items():
        if name == skip:
            continue
        text = msp.add_text(
            SECRET if name.startswith(("owner", "installer", "location")) else f"[{name}]",
            height=1.5,
            dxfattribs={
                "layer": "TEXTO",
                "style": "OpenSansCondensed-Bold" if name in CENTRED else "OpenSans",
            },
        )
        if name in CENTRED:
            text.set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)
        else:
            text.set_placement((x, y))
    if extra == "mtext":
        msp.add_mtext("x", dxfattribs={"layer": "TEXTO"})
    if extra == "layer":
        doc.layers.add("OTRA")
        msp.add_line((20, 20), (30, 30), dxfattribs={"layer": "OTRA"})
    return doc


@pytest.fixture(scope="module")
def template() -> SheetTemplate:
    return read_template(_template_doc())


def _sheet_spec(change: Any = None) -> dict[str, Any]:
    def edit(spec: dict[str, Any]) -> None:
        spec["layout"]["template"] = "a3_plantilla_v1"
        if change is not None:
            change(spec)

    return mutated(edit)


def _build(template: SheetTemplate, change: Any = None) -> Diagram:
    report = validate_pv_design(_sheet_spec(change))
    assert report.spec is not None, report
    return build_sheet_diagram(report.spec, report.derived, template)


@pytest.fixture(scope="module")
def diagram(template: SheetTemplate) -> Diagram:
    return _build(template)


def _one_string(spec: dict[str, Any]) -> None:
    spec["strings"] = spec["strings"][:1]
    spec["circuits"] = [c for c in spec["circuits"] if c["id"] != "C-S2"]


def _thirteen_each(spec: dict[str, Any]) -> None:
    for string in spec["strings"]:
        string["n_series"] = 13  # three rows per string (the layout limit, not a valid design)


LAYOUTS = [None, _one_string, _thirteen_each]
LAYOUT_IDS = ["two strings of 7", "one string", "two strings of 13"]


# --- Reader and neutral writer -------------------------------------------------------------------


def test_the_reader_finds_every_field_and_keeps_the_furniture(template: SheetTemplate) -> None:
    assert set(template.fields) == set(definition.FIELDS)
    assert [t.text for t in template.texts] == ["LATITUD:"]  # empty texts are dropped
    assert not template.lines  # the only line lies in the cleared symbology box
    assert len(template.polylines) == 4
    assert template.circles[0].radius == 3.2
    assert template.fields["title"].align == "center"
    assert template.fields["memory.1"].align == "left"


def test_template_layers_become_house_layers_with_their_lineweight(template: SheetTemplate) -> None:
    frame = template.polylines[0]
    assert (frame.layer, frame.lineweight) == ("G-ANNO-TTLB", 50)
    assert {t.layer for t in template.fields.values()} == {"E-ANNO-NOTE"}


def test_open_sans_is_replaced_by_arial_so_autocad_does_not_fall_back_to_simplex(
    template: SheetTemplate,
) -> None:
    assert dict(template.text_styles) == {
        "OpenSans": "arial.ttf",
        "OpenSansCondensed-Bold": "ARIALNB.TTF",
    }


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"skip": "memory.3"}, "memory.3"),
        ({"extra": "mtext"}, "unsupported MTEXT"),
        ({"extra": "layer"}, "'OTRA' has no house layer"),
    ],
)
def test_a_template_that_does_not_match_is_refused(kwargs: dict[str, Any], message: str) -> None:
    with pytest.raises(SheetTemplateError, match=re.escape(message)):
        read_template(_template_doc(**kwargs))


def test_the_neutral_template_has_placeholders_and_no_personal_data(
    template: SheetTemplate, tmp_path: Path
) -> None:
    data = write_template(template, tmp_path / "neutral.dxf")
    assert SECRET.encode() not in data
    assert b"{owner.name}" in data
    again = load_sheet_template("a3_plantilla_v1", tmp_path / "neutral.dxf")
    assert set(again.fields) == set(template.fields)
    assert again.fields["title"] == template.fields["title"]
    assert write_template(again, tmp_path / "twice.dxf") == data  # deterministic, stable


def test_loading_a_missing_or_unknown_template_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(SheetTemplateError, match="not found"):
        load_sheet_template("a3_plantilla_v1", tmp_path / "nope.dxf")
    with pytest.raises(SheetTemplateError, match="unknown sheet template"):
        load_sheet_template("a4_otra")


# --- Layout -------------------------------------------------------------------------------------


def _build_any(template: SheetTemplate, change: Any) -> Diagram:
    report = validate_pv_design(_sheet_spec(change))
    assert report.spec is not None
    return build_sheet_diagram(report.spec, report.derived, template)


@pytest.mark.parametrize("change", LAYOUTS, ids=LAYOUT_IDS)
def test_the_schematic_is_sound_and_stays_in_its_area(template: SheetTemplate, change: Any) -> None:
    diagram = _build_any(template, change)
    assert check_diagram(diagram) == []
    area = Box(*definition.SCHEMATIC_AREA)
    boxes = _model_boxes(diagram)
    for name, box in boxes:
        assert area.contains(box), f"{name} {box} leaves the schematic area"
    for (name_a, a), (name_b, b) in combinations(boxes, 2):
        assert not a.intersects(b, gap=MIN_GAP_MM), f"{name_a} overlaps {name_b}"
    for conn in diagram.connections:
        own = {conn.start.comp_id, conn.end.comp_id}
        for name, box in boxes:
            if name.removeprefix("symbol ").split(" ")[0].split(".")[0] in own:
                continue
            for a, b in zip(conn.points, conn.points[1:], strict=False):
                assert not _segment_hits(box, a, b), f"wire {conn.id} crosses {name}"


@pytest.mark.parametrize("change", LAYOUTS, ids=LAYOUT_IDS)
def test_every_module_is_drawn_and_each_string_runs_straight_into_its_mppt(
    template: SheetTemplate, change: Any
) -> None:
    diagram = _build_any(template, change)
    strings = [i for i in diagram.instances if i.symbol.startswith("PVSLD_PV_STRING_")]
    assert strings
    for item in strings:
        n_series = int(item.values["N_SERIES"])
        assert item.symbol.startswith(f"PVSLD_PV_STRING_{n_series}M_")
        modules = [g for g in get_symbol(item.symbol).geometry if getattr(g, "closed", False)]
        assert len(modules) == n_series
    string_ids = {item.comp_id for item in strings}
    for wire in (c for c in diagram.connections if c.start.comp_id in string_ids):
        assert len(wire.points) == 2
    if len(strings) == 2:  # the upper string grows up, the lower one down: they never meet
        assert [s.symbol[-2:] for s in strings] == ["UP", "DN"]


def test_the_protection_schedule_lists_every_device_in_the_template_style(
    diagram: Diagram,
) -> None:
    table = next(t for t in diagram.tables if t.id == "TBL-PROTECTIONS")
    assert [row[0] for row in table.rows] == ["ITM-1", "ITM-P", "DCD-1", "DPS-CD1", "DPS-CA1"]
    assert table.space == "model"
    assert Box(*definition.SCHEMATIC_AREA).contains(table.box())
    title = table.texts()[0]
    assert (title.align, title.style, title.height) == ("center", "OpenSansCondensed-Bold", 2.2)
    assert {t.style for t in table.texts()[1:]} == {"OpenSans"}


def test_circuits_are_numbered_with_the_template_markers(diagram: Diagram) -> None:
    numbers = sorted(t.text for t in diagram.texts if t.space == "model" and t.align == "center")
    assert numbers == ["1", "1", "2"]  # two strings, one inverter output
    markers = [c for c in diagram.circles if c.space == "model"]
    assert len(markers) == 3
    assert all(c.radius == definition.MARKER_RADIUS_MM for c in markers)


def test_no_personal_data_reaches_the_sheet(diagram: Diagram) -> None:
    text = "\n".join(t.text for t in diagram.texts)
    for secret in (
        SECRET,
        "Juan Pérez",
        "cliente@example.com",
        "+52 33",
        "Av. Ejemplo",
        "Zapopan",
        "45000",
        "20.72",
        "103.39",
        "Ing. Nombre Apellido",
        "00000000",
        "Integrador S.A.",
        "A00000",
    ):
        assert secret not in text, secret
    values = {t.text for t in diagram.texts}
    assert COMPANY in values
    assert "WGS84" in values


def test_every_field_is_written_once_with_the_design_values(diagram: Diagram) -> None:
    paper = [t for t in diagram.texts if t.space == "paper"]
    anchored = {(round(t.x, 2), round(t.y, 2)) for t in paper}
    for name, (x, y) in definition.FIELDS.items():
        assert (x, y) in anchored, name
    values = {t.text for t in paper}
    assert "SISTEMA FOTOVOLTAICO INTERCONECTADO A LA RED DE 7.7 kWp" in values
    assert "7,700 Wp" in values
    assert "6,000 W" in values
    assert "1.28" in values
    assert "BT 2F-3H 220/127 V  -  Medición neta" in values
    assert "IE-01   HOJA 1 DE 1   REV. A" in values
    assert "05-OCT-2026" in values
    assert "2 cadenas de 7 módulos en serie" in values
    assert any("DPS-CA1 T2 en CC-1" in v for v in values)
    assert any(
        v.startswith("      Regla 120 % (705-12(d)(2)): 125 A x 1.20 = 150 A") for v in values
    )


def test_the_symbology_shows_each_block_drawn_inside_its_box(diagram: Diagram) -> None:
    drawn = list(
        dict.fromkeys(
            "PVSLD_PV_MODULE" if i.symbol.startswith("PVSLD_PV_STRING") else i.symbol
            for i in diagram.instances
        )
    )
    symbology = [s for s in diagram.samples if s.space == "paper"]  # not the junction dots
    assert [s.symbol for s in symbology] == drawn  # a full string shows as one module
    x0, y0, x1, y1 = definition.SYMBOLOGY_BOX
    for sample in symbology:
        assert x0 < sample.x < x1
        assert y0 < sample.y < y1
        assert 0 < sample.scale <= 1


def test_a_value_too_long_for_its_box_is_refused(template: SheetTemplate) -> None:
    def long_model(spec: dict[str, Any]) -> None:
        spec["modules"][0]["model"] = "JKM" + "X" * 60

    with pytest.raises(LayoutError, match="module"):
        _build(template, long_model)


def test_the_sheet_renders_reads_back_and_is_deterministic(diagram: Diagram) -> None:
    first = render_dxf(diagram)
    report = verify(diagram, first.data)
    assert report.ok, report.problems
    assert render_dxf(diagram).data == first.data
    doc = first.document
    assert doc.styles.get("OpenSans").dxf.font == "arial.ttf"
    samples = [
        e
        for e in doc.modelspace()
        if e.dxftype() == "INSERT" and e.dxf.xscale < 1 and not e.attribs
    ]
    assert len(samples) == len(diagram.samples)


def test_everything_is_editable_in_model_space_and_the_file_opens_there(diagram: Diagram) -> None:
    doc = render_dxf(diagram).document
    assert doc.header["$TILEMODE"] == 1  # AutoCAD opens the Model tab, where the whole sheet is
    sheet = doc.layouts.get("A3")
    assert {e.dxftype() for e in sheet} == {"VIEWPORT"}  # the layout only plots the model
    texts = {e.dxf.text for e in doc.modelspace().query("TEXT")}
    assert COMPANY in texts  # the template furniture
    assert "LATITUD:" in texts  # a fixed text of the (synthetic) template
    assert {e.dxf.name for e in doc.modelspace().query("INSERT")} >= {"PVSLD_INV", "PVSLD_CB"}
    unlocked = [layer.dxf.name for layer in doc.layers if not layer.is_locked()]
    assert len(unlocked) == len(list(doc.layers))


def test_the_service_lays_out_with_the_sheet_template_it_names(
    template: SheetTemplate, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_template(template, tmp_path / "a3.dxf")
    monkeypatch.setenv(ENV_SHEET_TEMPLATE, str(tmp_path / "a3.dxf"))
    report = validate_pv_design(_sheet_spec())
    assert report.spec is not None
    diagram = layout_diagram(report.spec, report.derived)
    assert diagram.template == "a3_plantilla_v1"
    assert ("SHEET_TEMPLATE", "a3_plantilla_v1") in diagram.metadata


# --- Import ---------------------------------------------------------------------------------------


def test_import_from_dxf_writes_the_neutral_template(tmp_path: Path) -> None:
    source = tmp_path / "plantilla.dxf"
    _template_doc().saveas(source)
    template, output = import_template(source, "a3_plantilla_v1", tmp_path / "out.dxf")
    assert output.is_file()
    assert SECRET.encode() not in output.read_bytes()
    assert len(template.fields) == len(definition.FIELDS)


def test_the_sheet_cli_imports_and_checks(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "plantilla.dxf"
    _template_doc().saveas(source)
    assert main(["sheet", "import", str(source), "-o", str(tmp_path / "a3.dxf")]) == 0
    assert "76 fields" in capsys.readouterr().out
    assert main(["sheet", "check", str(tmp_path / "a3.dxf")]) == 0
    assert main(["sheet", "check", str(tmp_path / "missing.dxf")]) == 1
    assert "not found" in capsys.readouterr().err


def test_dwg_conversion_script_and_missing_core_console(tmp_path: Path) -> None:
    script = dxfout_script(Path("C:/plantillas/salida.dxf"))
    assert script.splitlines() == [
        '(setvar "FILEDIA" 0)',
        "_.DXFOUT",
        str(Path("C:/plantillas/salida.dxf")),
        "16",
        "_.QUIT",
        "_Y",
    ]
    with pytest.raises(SheetTemplateError, match="accoreconsole"):
        dwg_to_dxf(tmp_path / "a.dwg", tmp_path / "a.dxf", accoreconsole=tmp_path / "none.exe")


# --- The committed neutral template ------------------------------------------------------------


@pytest.mark.parametrize("change", LAYOUTS, ids=LAYOUT_IDS)
def test_the_committed_template_holds_the_schematic_without_touching_its_texts(
    change: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv(ENV_SHEET_TEMPLATE, raising=False)
    real = load_sheet_template("a3_plantilla_v1")  # sheet_templates/a3_plantilla_v1.dxf
    assert set(real.fields) == set(definition.FIELDS)
    assert len(real.texts) > 50
    assert not any(SECRET in t.text for t in real.texts)
    diagram = _build_any(real, change)
    model = _model_boxes(diagram)
    for text in (t for t in diagram.texts if t.space == "paper" and t.text):
        for name, box in model:
            assert not text.box().intersects(box), f"sheet text {text.text!r} overlaps {name}"


# --- DC protection box (owner decisions 2026-10-08) -----------------------------------------


def _box(kind: str, *, switch: bool = True) -> Any:
    """What the sizing engine writes: a protection per string (FUS- or DCB-) and the box
    disconnect; without ``switch`` the sample's integrated DCD-1 stays the only disconnect."""

    def change(spec: dict[str, Any]) -> None:
        prefix = {"fuse": "FUS", "breaker": "DCB"}[kind]
        devices = [
            {"id": f"{prefix}-S{n}", "integrated_in": None, "poles": 2, "ue_v": 1000, "ie_a": 25}
            for n in (1, 2)
        ]
        if switch:
            spec["dc_bos"]["disconnects"] = [
                *devices,
                {"id": "DCD-CD1", "integrated_in": None, "poles": 4, "ue_v": 1000, "ie_a": 25},
            ]
        else:
            spec["dc_bos"]["disconnects"] += devices

    return change


def _outline(diagram: Diagram) -> Box:
    box = next(p for p in diagram.polylines if p.layer == "E-ANNO-ENCL" and p.space == "model")
    xs = [p.x for p in box.points]
    ys = [p.y for p in box.points]
    return Box(min(xs), min(ys), max(xs), max(ys))


@pytest.mark.parametrize(
    ("kind", "symbol"), [("fuse", "PVSLD_FUSE_DISC_DC"), ("breaker", "PVSLD_CB_DC")]
)
def test_the_box_follows_the_reference_connector_protection_spd_then_one_disconnect(
    template: SheetTemplate, kind: str, symbol: str
) -> None:
    prefix = {"fuse": "FUS", "breaker": "DCB"}[kind]
    diagram = _build(template, _box(kind))
    assert check_diagram(diagram) == []
    by_id = {i.comp_id: i for i in diagram.instances}
    assert by_id["DCD-CD1"].symbol == "PVSLD_DC_DISCONNECT_2S"  # one ganged switch
    assert by_id["DPS-CD1"].symbol == "PVSLD_SPD_DC_BOX"
    path = [
        ((c.start.comp_id, c.start.port), (c.end.comp_id, c.end.port)) for c in diagram.connections
    ]
    for n, mppt in ((1, "A"), (2, "B")):
        device = f"{prefix}-S{n}"
        assert by_id[device].symbol == symbol
        assert by_id[f"CX-S{n}"].symbol == "PVSLD_PV_CONNECTOR"
        for chain in (
            (("S" + str(n), "OUT"), (f"CX-S{n}", "IN")),
            ((f"CX-S{n}", "OUT"), (f"XE-S{n}", "L")),
            ((f"XE-S{n}", "R"), (device, "IN")),
            ((device, "OUT"), ("DCD-CD1", f"IN{n}")),
            (("DCD-CD1", f"OUT{n}"), (f"XS-S{n}", "L")),
            ((f"XS-S{n}", "R"), ("INV1", mppt)),
        ):
            assert chain in path
    # The string circuit (and its marker) is the run from the field connector to the box.
    run = next(c for c in diagram.connections if c.circuit_id == "C-S1")
    assert (run.start.comp_id, run.end.comp_id) == ("CX-S1", "XE-S1")
    feeds = {
        ((c.start.comp_id, c.start.port), c.end.port)
        for c in diagram.connections
        if c.end.comp_id == "DPS-CD1"
    }
    assert feeds == {((f"{prefix}-S1", "OUT"), "L1"), ((f"{prefix}-S2", "OUT"), "L2")}
    assert any(c.start.comp_id == "DPS-CD1" and c.kind == "grounding" for c in diagram.connections)
    # Junction dots where each tap leaves its string; the upper tap crosses the lower string.
    dots = {(s.x, s.y) for s in diagram.samples if s.symbol == "PVSLD_JUNCTION"}
    spd = by_id["DPS-CD1"]
    assert dots == {
        (spd.port_xy("L1").x, by_id[f"{prefix}-S1"].port_xy("OUT").y),
        (spd.port_xy("L2").x, by_id[f"{prefix}-S2"].port_xy("OUT").y),
    }
    captions = [t.text for t in diagram.texts if t.text.endswith("PROTECCIONES CD")]
    assert captions == ["CAJA DE PROTECCIONES CD"]
    inside = _outline(diagram)
    for comp_id, item in by_id.items():
        if comp_id.split("-")[0] in ("XE", "XS"):  # the box terminals sit on its sides
            assert item.layer == "E-PVDC-COND"  # BYBLOCK colour: DC blue, not the AC red
            assert item.port_xy("L").x < (inside.x0 if comp_id[:2] == "XE" else inside.x1)
            assert item.port_xy("R").x > (inside.x0 if comp_id[:2] == "XE" else inside.x1)
        elif comp_id.split("-")[0] in (prefix, "DPS", "DCD"):
            for name, part in item.boxes():
                if name != "DPS-CD1 symbol":  # its earth lead leaves the box
                    assert inside.contains(part), f"{name} {part} leaves the box"
    for n in (1, 2):  # the field connector, then the marked run, then the box
        assert by_id[f"S{n}"].port_xy("OUT").x < by_id[f"CX-S{n}"].x
        assert by_id[f"CX-S{n}"].port_xy("OUT").x + 6 < inside.x0
    assert inside.x1 < by_id["INV1"].x
    table = next(t for t in diagram.tables if t.title == "CUADRO DE PROTECCIONES")
    rows = {r[0]: r for r in table.rows}
    assert rows["DCD-CD1"][2] == "4"
    assert (
        rows[f"{prefix}-S1"][1]
        == {"fuse": "Fusible gPV (cadena)", "breaker": "ITM de CD (cadena)"}[kind]
    )
    assert {rows[i][-1] for i in ("DCD-CD1", f"{prefix}-S1", f"{prefix}-S2")} == {"Caja CD"}


def test_an_integrated_disconnect_stays_outside_the_box(template: SheetTemplate) -> None:
    diagram = _build(template, _box("fuse", switch=False))
    assert check_diagram(diagram) == []
    inside = _outline(diagram)
    poles = [i for i in diagram.instances if i.comp_id.startswith("DCD-1/")]
    assert len(poles) == 2
    assert all(item.x > inside.x1 for item in poles)
    assert [p.values["TAG"] for p in poles] == ["DCD-1", ""]  # one tag, on the upper pole


def test_without_string_protection_the_spd_hangs_before_the_disconnect(
    template: SheetTemplate,
) -> None:
    diagram = _build(template)  # the sample: DCD-1 integrated in the inverter, no protection
    spd = next(c for c in diagram.connections if c.end.comp_id == "DPS-CD1")
    assert (spd.start.comp_id, spd.start.port) == ("DCD-1/S1", "IN")
    assert not any(t.text.endswith("PROTECCIONES CD") for t in diagram.texts)  # no box


@pytest.mark.parametrize(
    ("kind", "text"),
    [
        ("fuse", "Fusible gPV 25 A por cadena en la caja de protecciones CD"),
        ("breaker", "ITM CD 25 A por cadena en la caja de protecciones CD"),
    ],
)
def test_the_calculation_summary_names_the_string_protection(
    template: SheetTemplate, kind: str, text: str
) -> None:
    texts = {t.text for t in _build(template, _box(kind)).texts}
    assert any(text in t for t in texts)
    assert not any("fusible de cadena no requerido" in t for t in texts)
