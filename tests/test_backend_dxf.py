"""The ezdxf backend: file structure, semantics read back from the DXF, and the verifier itself."""

from __future__ import annotations

import re
import time
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import ezdxf
import pytest
from ezdxf.document import Drawing
from ezdxf.entities import Viewport

from pvsld.backends.base import RenderBackend, sha256_hex
from pvsld.backends.dxf import (
    LAYOUT_NAME,
    DxfBackend,
    DxfOutput,
    render_dxf,
    write_dxf,
)
from pvsld.backends.readback import ReadBackReport, load_document, read_inventory, verify
from pvsld.core import layers
from pvsld.core.diagram import Diagram
from pvsld.core.layout import build_diagram
from pvsld.core.validation import validate_pv_design
from pvsld.symbols import get_symbol
from s1_helpers import load_example


@pytest.fixture(scope="module")
def diagram() -> Diagram:
    report = validate_pv_design(load_example())
    assert report.spec is not None
    assert report.derived is not None
    return build_diagram(report.spec, report.derived)


@pytest.fixture(scope="module")
def output(diagram: Diagram) -> DxfOutput:
    return render_dxf(diagram)


@pytest.fixture
def doc(output: DxfOutput) -> Drawing:
    """A fresh document re-read from the bytes, so tests may mutate it."""
    return load_document(output.data)


# --- File format ------------------------------------------------------------------------------


def test_the_file_is_dxf_r2018_in_millimetres(doc: Drawing) -> None:
    assert doc.header["$ACADVER"] == "AC1032"
    assert doc.dxfversion == "AC1032"
    assert doc.header["$INSUNITS"] == 4
    assert doc.header["$MEASUREMENT"] == 1


def test_newlines_are_lf_and_text_is_utf_8_on_every_platform(output: DxfOutput) -> None:
    assert b"\r" not in output.data
    assert output.data.endswith(b"EOF\n")
    text = output.data.decode("utf-8")
    assert "Emisión para solicitud de interconexión" in text
    assert "CÉDULA PROF." in text
    assert "\\U+" not in text  # no escaped accents


def test_audit_reports_no_errors_and_no_fixes(doc: Drawing) -> None:
    auditor = doc.audit()
    assert len(auditor.errors) == 0
    assert len(auditor.fixes) == 0


def test_the_in_memory_document_also_audits_clean(output: DxfOutput) -> None:
    auditor = output.document.audit()
    assert (len(auditor.errors), len(auditor.fixes)) == (0, 0)


def test_a_paper_space_a3_layout_with_a_one_to_one_viewport(doc: Drawing) -> None:
    assert LAYOUT_NAME in doc.layouts.names()
    layout = doc.layouts.get(LAYOUT_NAME)
    assert (layout.dxf_layout.dxf.paper_width, layout.dxf_layout.dxf.paper_height) == (420, 297)
    viewports = [v for v in layout.viewports() if v.dxf.layer == layers.NON_PLOT]
    assert viewports, "no viewport on the non-plot layer"
    floating = [v for v in viewports if v.dxf.width == 400]
    assert len(floating) == 1
    vp = floating[0]
    assert vp.dxf.height / vp.dxf.view_height == pytest.approx(1.0)  # scale 1:1
    assert (vp.dxf.center.x, vp.dxf.center.y) == (
        vp.dxf.view_center_point.x,
        vp.dxf.view_center_point.y,
    )


def _overall_viewport(doc: Drawing) -> Viewport:
    """The overall paper-space viewport (id 1) of the A3 layout, as AutoCAD identifies it."""
    found = [v for v in doc.layouts.get(LAYOUT_NAME).viewports() if v.dxf.id == 1]
    assert len(found) == 1, "the A3 layout must hold exactly one overall viewport (id 1)"
    return found[0]


def _entities_on_layer_zero(doc: Drawing) -> list[ezdxf.entities.DXFGraphic]:
    """Every entity on layer 0, in every layout, block definition and INSERT attribute."""
    found = []
    for layout in doc.layouts:
        for entity in layout:
            found.append(entity)
            found.extend(entity.attribs if entity.dxftype() == "INSERT" else [])
    for block in doc.blocks:
        if not block.name.startswith("*"):
            found.extend(block)
    return [e for e in found if e.dxf.layer == "0"]


def test_the_overall_paper_space_viewport_is_the_only_entity_on_layer_zero(doc: Drawing) -> None:
    # AutoCAD's AUDIT rejects the overall viewport on any other layer ("Paperspace vport layer
    # Not 0", S4); every other entity must still stay off layer 0.
    on_layer_zero = _entities_on_layer_zero(doc)
    assert [(e.dxftype(), e.dxf.handle) for e in on_layer_zero] == [
        ("VIEWPORT", _overall_viewport(doc).dxf.handle)
    ]
    assert _overall_viewport(doc).dxf.layer == layers.OVERALL_VIEWPORT == "0"


def test_the_detail_viewport_stays_on_the_non_plot_layer(doc: Drawing) -> None:
    detail = [v for v in doc.layouts.get(LAYOUT_NAME).viewports() if v.dxf.id != 1]
    assert len(detail) == 1
    assert detail[0].dxf.layer == layers.NON_PLOT


def test_the_a3_layout_names_a_canonical_a3_landscape_medium(doc: Drawing) -> None:
    # S4: the old name ISO_A3_(420.00_x_297.00_MM)_(420.00_x_297.00_MM) is no media name of
    # "DWG To PDF.pc3". The canonical full-bleed A3 name matches the zero margins and 420 x 297.
    settings = doc.layouts.get(LAYOUT_NAME).dxf_layout.dxf
    assert settings.paper_size == "ISO_full_bleed_A3_(420.00_x_297.00_MM)"
    assert re.fullmatch(r"ISO_full_bleed_A3_\(420\.00_x_297\.00_MM\)", settings.paper_size)
    assert (settings.paper_width, settings.paper_height) == (420, 297)  # landscape
    assert settings.plot_paper_units == 1  # millimetres
    assert settings.plot_rotation == 0
    assert (
        settings.left_margin,
        settings.bottom_margin,
        settings.right_margin,
        settings.top_margin,
    ) == (0, 0, 0, 0)
    assert settings.plot_configuration_file == "DWG To PDF.pc3"


def test_the_title_block_lives_in_paper_space_the_schematic_in_model_space(doc: Drawing) -> None:
    paper_blocks = [e.dxf.name for e in doc.layouts.get(LAYOUT_NAME) if e.dxftype() == "INSERT"]
    model_blocks = [e.dxf.name for e in doc.modelspace() if e.dxftype() == "INSERT"]
    assert paper_blocks == ["PVSLD_TTLB"]
    assert "PVSLD_TTLB" not in model_blocks
    assert len(model_blocks) == 10


# --- Layers -----------------------------------------------------------------------------------


def test_every_house_layer_is_defined_with_its_colour_weight_and_linetype(doc: Drawing) -> None:
    for layer in layers.LAYERS:
        entry = doc.layers.get(layer.name)
        assert entry.dxf.color == layer.aci
        assert entry.dxf.lineweight == layer.lineweight
        assert entry.dxf.linetype.upper() == layer.linetype
        assert entry.dxf.plot == (1 if layer.plot else 0) or layer.plot
    assert doc.layers.get(layers.NON_PLOT).dxf.plot == 0


def test_the_metric_dashed_linetypes_exist(doc: Drawing) -> None:
    assert doc.linetypes.get("DASHED").dxf.description.startswith("Dashed")
    assert doc.linetypes.has_entry("DASHDOT")


def test_no_entity_lies_on_layer_zero_and_all_layers_are_standard(doc: Drawing) -> None:
    inventory = read_inventory(doc)
    assert inventory.layer_zero_entities == 0  # drawing content; the overall viewport is apart
    assert inventory.overall_viewport_layers == {LAYOUT_NAME: "0"}
    assert set(inventory.layer_counts) <= layers.LAYER_NAMES
    assert "Defpoints" not in inventory.layer_counts
    assert "VIEWPORTS" not in inventory.layer_counts


# --- Blocks, attributes, identity -------------------------------------------------------------


def test_insert_count_per_block_equals_the_model_count(doc: Drawing, diagram: Diagram) -> None:
    inventory = read_inventory(doc)
    assert dict(Counter(i.block for i in inventory.inserts)) == diagram.block_counts()


def test_only_the_used_symbols_are_defined_as_blocks(doc: Drawing, diagram: Diagram) -> None:
    defined = {b.name for b in doc.blocks if not b.name.startswith("*")}
    assert defined == set(diagram.block_counts())


def test_every_attribute_round_trips_by_comp_id(doc: Drawing, diagram: Diagram) -> None:
    inventory = read_inventory(doc)
    by_id = {i.comp_id: i for i in inventory.inserts}
    assert set(by_id) == {i.comp_id for i in diagram.instances}
    total = 0
    for item in diagram.instances:
        assert by_id[item.comp_id].attributes == item.values
        assert by_id[item.comp_id].xdata_comp_id == item.comp_id
        total += len(item.values)
    assert total == 157  # 11 components, every ATTRIB compared


def test_attribute_values_keep_spanish_accents_and_units(doc: Drawing) -> None:
    inventory = read_inventory(doc)
    values = {i.comp_id: i.attributes for i in inventory.inserts}
    assert values["INV1"]["DESC"] == "Inversor de red 6.0 kW, 220 V"
    assert values["TTLB-1"]["UBICACION"].endswith("C.P. 45000")
    assert values["TTLB-1"]["ESCALA"] == "SIN ESCALA"
    assert values["S1"]["DESC"] == "7 × 550 W = 3.85 kWp"


def test_hidden_attributes_are_invisible_and_visible_ones_are_not(doc: Drawing) -> None:
    insert = next(
        e for e in doc.modelspace() if e.dxftype() == "INSERT" and e.dxf.name == "PVSLD_CB"
    )
    flags = {a.dxf.tag: a.is_invisible for a in insert.attribs}
    assert all(flags[tag] for tag in ("COMP_ID", "IEC_REF", "NMX_REF"))
    assert not any(flags[tag] for tag in ("TAG", "DESC", "ROLE"))


def test_block_definitions_carry_their_attribute_definitions_and_ports(doc: Drawing) -> None:
    for name in {e.dxf.name for e in doc.modelspace() if e.dxftype() == "INSERT"}:
        symbol = get_symbol(name)
        block = doc.blocks.get(name)
        assert [a.dxf.tag for a in block.attdefs()] == list(symbol.tags)
        stored = read_inventory(doc).block_ports[name]
        assert [(p.id, p.kind, p.direction, p.x, p.y, p.required) for p in stored] == [
            (p.id, p.kind, p.direction, p.x, p.y, p.required) for p in symbol.ports
        ]


def test_text_uses_the_truetype_style_and_is_at_least_2_5_mm_high(doc: Drawing) -> None:
    assert doc.styles.get("PVSLD_STD").dxf.font == "arial.ttf"
    heights = [t.dxf.height for t in doc.modelspace().query("TEXT")]
    assert heights
    assert min(heights) >= 2.5
    assert all(t.dxf.style == "PVSLD_STD" for t in doc.modelspace().query("TEXT"))


def test_project_metadata_is_stored_without_the_package_version(doc: Drawing) -> None:
    assert doc.header["$PROJECTNAME"] == "PV-2026-0001"
    meta = doc.ezdxf_metadata()
    assert meta["PVSLD_RULEPACK"] == "mx-gd-2026.10"
    assert meta["PVSLD_LAYOUT_TEMPLATE"] == "bt_string_residential_v1"


# --- Connectivity read back from the file -----------------------------------------------------


def test_conductors_are_lwpolylines_with_connectivity_xdata(doc: Drawing, diagram: Diagram) -> None:
    inventory = read_inventory(doc)
    assert [w.conn_id for w in inventory.wires] == [c.id for c in diagram.connections]
    first = inventory.wires[0]
    assert (first.start, first.end, first.circuit_id) == ("S1.OUT", "INV1.A", "C-S1")
    assert first.layer == layers.DC_CONDUCTORS


def test_the_verifier_confirms_every_s1_criterion(output: DxfOutput, diagram: Diagram) -> None:
    report = verify(diagram, output.data)
    assert report.problems == ()
    assert report.ok
    assert (report.audit_errors, report.audit_fixes) == (0, 0)
    assert report.insert_counts == report.expected_counts
    assert report.attributes_matched == report.attributes_checked == 157
    assert report.instances_matched == report.instances_checked == 11
    assert report.required_ports == 18
    assert report.dangling_ports == ()
    assert report.wire_ends_checked == 20
    assert report.wire_ends_off_port == ()
    assert report.layer_zero_entities == 0


def test_verify_accepts_bytes_a_path_and_a_document(
    output: DxfOutput, diagram: Diagram, tmp_path: Path
) -> None:
    path = tmp_path / "sld.dxf"
    path.write_bytes(output.data)
    assert verify(diagram, path).ok
    assert verify(diagram, load_document(output.data)).ok


def test_the_summary_is_plain_json(output: DxfOutput, diagram: Diagram) -> None:
    import json

    summary = verify(diagram, output.data).summary()
    json.dumps(summary)
    assert summary["attribute_roundtrip"] == "157/157"
    assert summary["entities_on_layer_0"] == 0


# --- The verifier can fail (it is not a rubber stamp) -----------------------------------------


def _verify_mutated(
    output: DxfOutput, diagram: Diagram, mutate: Callable[[Drawing], None]
) -> ReadBackReport:
    document = load_document(output.data)
    mutate(document)
    return verify(diagram, document)


def _insert(doc: Drawing, comp_id: str):  # type: ignore[no-untyped-def]
    for entity in doc.modelspace():
        if entity.dxftype() == "INSERT" and any(
            a.dxf.tag == "COMP_ID" and a.dxf.text == comp_id for a in entity.attribs
        ):
            return entity
    raise AssertionError(comp_id)


def test_verify_catches_a_changed_attribute_value(output: DxfOutput, diagram: Diagram) -> None:
    def change(doc: Drawing) -> None:
        next(a for a in _insert(doc, "ITM-1").attribs if a.dxf.tag == "RATING_A").dxf.text = "40"

    report = _verify_mutated(output, diagram, change)
    assert not report.ok
    assert report.attributes_matched == report.attributes_checked - 1
    assert any("ITM-1" in p for p in report.problems)


def test_verify_catches_a_missing_component(output: DxfOutput, diagram: Diagram) -> None:
    report = _verify_mutated(
        output, diagram, lambda doc: doc.modelspace().delete_entity(_insert(doc, "M-1"))
    )
    assert not report.ok
    assert any("M-1" in p for p in report.problems)
    assert report.insert_counts != report.expected_counts


def test_verify_catches_an_extra_insert(output: DxfOutput, diagram: Diagram) -> None:
    report = _verify_mutated(
        output,
        diagram,
        lambda doc: doc.modelspace().add_blockref(
            "PVSLD_CB", (300, 100), dxfattribs={"layer": layers.AC_EQUIPMENT}
        ),
    )
    assert any("INSERT counts" in p for p in report.problems)


def test_verify_catches_a_wire_end_moved_off_its_port(output: DxfOutput, diagram: Diagram) -> None:
    def move(doc: Drawing) -> None:
        wire = next(e for e in doc.modelspace().query("LWPOLYLINE") if e.get_xdata("PVSLD"))
        points = list(wire.get_points("xy"))
        points[0] = (points[0][0] + 0.5, points[0][1])
        wire.set_points(points)

    report = _verify_mutated(output, diagram, move)
    assert not report.ok
    assert report.wire_ends_off_port
    assert "S1.OUT" in report.wire_ends_off_port[0]
    assert "S1.OUT" in report.dangling_ports


def test_verify_accepts_a_wire_end_within_tolerance(output: DxfOutput, diagram: Diagram) -> None:
    def nudge(doc: Drawing) -> None:
        wire = next(e for e in doc.modelspace().query("LWPOLYLINE") if e.get_xdata("PVSLD"))
        points = list(wire.get_points("xy"))
        points[0] = (points[0][0] + 0.004, points[0][1])
        wire.set_points(points)

    # the point differs from the model by 0.004 mm: still on the port, but not equal to the model
    report = _verify_mutated(output, diagram, nudge)
    assert report.wire_ends_off_port == ()
    assert report.dangling_ports == ()
    assert any("conductor C-S1 differs from the model" in p for p in report.problems)


def test_verify_catches_a_deleted_wire_as_a_dangling_port(
    output: DxfOutput, diagram: Diagram
) -> None:
    def delete(doc: Drawing) -> None:
        wire = next(e for e in doc.modelspace().query("LWPOLYLINE") if e.get_xdata("PVSLD"))
        doc.modelspace().delete_entity(wire)

    report = _verify_mutated(output, diagram, delete)
    assert "S1.OUT" in report.dangling_ports
    assert "INV1.A" in report.dangling_ports


def test_verify_catches_an_entity_on_layer_zero_in_a_layout_and_in_a_block(
    output: DxfOutput, diagram: Diagram
) -> None:
    in_layout = _verify_mutated(
        output,
        diagram,
        lambda doc: doc.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "0"}),
    )
    assert in_layout.layer_zero_entities == 1
    assert any("layer 0" in p for p in in_layout.problems)

    in_block = _verify_mutated(
        output,
        diagram,
        lambda doc: doc.blocks.get("PVSLD_CB").add_line((0, 0), (1, 1), dxfattribs={"layer": "0"}),
    )
    assert in_block.layer_zero_entities == 1


def test_verify_catches_a_foreign_layer(output: DxfOutput, diagram: Diagram) -> None:
    def stray(doc: Drawing) -> None:
        doc.layers.add("MY-LAYER")
        doc.modelspace().add_line((0, 0), (1, 1), dxfattribs={"layer": "MY-LAYER"})

    report = _verify_mutated(output, diagram, stray)
    assert any("outside the house standard" in p and "MY-LAYER" in p for p in report.problems)


def test_verify_catches_an_audit_error(output: DxfOutput, diagram: Diagram) -> None:
    def break_it(doc: Drawing) -> None:
        # an INSERT of a block that does not exist is an audit error that audit() deletes
        doc.modelspace().add_blockref("NO_SUCH_BLOCK", (0, 0), dxfattribs={"layer": layers.TAGS})

    report = _verify_mutated(output, diagram, break_it)
    assert report.audit_errors + report.audit_fixes > 0
    assert any("audit" in p for p in report.problems)


# --- Determinism ------------------------------------------------------------------------------


def test_two_runs_are_byte_identical(diagram: Diagram) -> None:
    first = render_dxf(diagram)
    second = render_dxf(diagram)
    assert first.data == second.data
    assert first.sha256 == second.sha256 == sha256_hex(first.data)


def test_a_diagram_rebuilt_from_the_spec_gives_the_same_bytes(output: DxfOutput) -> None:
    report = validate_pv_design(load_example())
    assert report.spec is not None
    assert render_dxf(build_diagram(report.spec)).data == output.data


def test_non_deterministic_mode_stamps_fresh_metadata(diagram: Diagram) -> None:
    first = render_dxf(diagram, deterministic=False)
    time.sleep(0.01)
    second = render_dxf(diagram, deterministic=False)
    assert first.data != second.data
    assert first.data != render_dxf(diagram).data


def test_verify_demands_the_overall_viewport_on_layer_zero(
    output: DxfOutput, diagram: Diagram
) -> None:
    report = _verify_mutated(
        output,
        diagram,
        lambda doc: setattr(_overall_viewport(doc).dxf, "layer", layers.NON_PLOT),
    )
    assert not report.ok
    assert any("overall viewport" in p and "layer 0" in p for p in report.problems)
    assert report.layer_zero_entities == 0  # a misplaced viewport is not drawing content


def test_verify_demands_an_overall_viewport(output: DxfOutput, diagram: Diagram) -> None:
    report = _verify_mutated(
        output,
        diagram,
        lambda doc: doc.layouts.get(LAYOUT_NAME).delete_entity(_overall_viewport(doc)),
    )
    assert any("no overall viewport" in p for p in report.problems)


def test_verify_still_flags_a_detail_viewport_on_layer_zero(
    output: DxfOutput, diagram: Diagram
) -> None:
    def move(doc: Drawing) -> None:
        detail = next(v for v in doc.layouts.get(LAYOUT_NAME).viewports() if v.dxf.id != 1)
        detail.dxf.layer = "0"

    report = _verify_mutated(output, diagram, move)
    assert report.layer_zero_entities == 1
    assert any("1 entities on layer 0" in p for p in report.problems)


def test_fixed_metadata_does_not_leak_into_later_renders(diagram: Diagram) -> None:
    assert ezdxf.options.write_fixed_meta_data_for_testing is False
    render_dxf(diagram)
    assert ezdxf.options.write_fixed_meta_data_for_testing is False


def test_the_option_is_restored_even_when_rendering_fails(diagram: Diagram) -> None:
    broken = Diagram(
        sheet=diagram.sheet,
        template=diagram.template,
        metadata=diagram.metadata,
        instances=(),
        connections=(),
        texts=(),
        lines=(),
        polylines=(),
        tables=(),
        viewport=None,  # type: ignore[arg-type]
    )
    with pytest.raises(AttributeError):
        render_dxf(broken)
    assert ezdxf.options.write_fixed_meta_data_for_testing is False


# --- Writing, the backend interface and the symbol library ------------------------------------


def test_write_dxf_writes_exactly_the_rendered_bytes(diagram: Diagram, tmp_path: Path) -> None:
    path = tmp_path / "deep" / "folder" / "sld.dxf"
    written = write_dxf(diagram, path)
    assert path.read_bytes() == written.data
    assert b"\r" not in path.read_bytes()


def test_the_backend_satisfies_the_render_backend_protocol(
    diagram: Diagram, tmp_path: Path
) -> None:
    backend: RenderBackend = DxfBackend()
    result = backend.render(diagram, tmp_path / "sld.dxf")
    assert result.backend == "ezdxf"
    assert result.size_bytes == (tmp_path / "sld.dxf").stat().st_size
    assert result.sha256 == sha256_hex((tmp_path / "sld.dxf").read_bytes())


def test_blocks_are_imported_from_the_symbol_library_with_their_ports(diagram: Diagram) -> None:
    from pvsld.symbols.cfe.loader import library_document

    doc = render_dxf(diagram).document
    library = library_document()
    used = {item.symbol for item in diagram.instances}
    assert {b.name for b in doc.blocks if b.name.startswith("PVSLD_")} == used
    for name in used:
        ours = [(e.dxftype(), e.dxf.layer) for e in doc.blocks.get(name)]
        theirs = [(e.dxftype(), e.dxf.layer) for e in library.blocks.get(name)]
        assert ours == theirs, name
        ports = [(t.code, t.value) for t in doc.blocks.get(name).block_record.get_xdata("PVSLD")]
        expected = library.blocks.get(name).block_record.get_xdata("PVSLD")
        assert ports == [(t.code, t.value) for t in expected], name
    assert "CERT" not in get_symbol("PVSLD_INV").tags


def test_a_combiner_is_defined_for_its_string_count_next_to_library_blocks() -> None:
    from pvsld.backends.dxf import _new_document, define_symbol_blocks

    doc = _new_document()
    define_symbol_blocks(
        doc, ["PVSLD_COMBINER_3S", "PVSLD_CB", "PVSLD_CB", "PVSLD_PV_STRING_7M_DN"]
    )
    assert {b.name for b in doc.blocks if b.name.startswith("PVSLD_")} == {
        "PVSLD_CB",
        "PVSLD_COMBINER_3S",
        "PVSLD_PV_STRING_7M_DN",
    }
    xdata = doc.blocks.get("PVSLD_COMBINER_3S").block_record.get_xdata("PVSLD")
    assert [t.value for t in xdata][:3] == ["pvsld.block/1", "0.6.0", 5]  # IN1-IN3, OUT, PE
    with pytest.raises(KeyError, match="PVSLD_NOPE"):
        define_symbol_blocks(doc, ["PVSLD_NOPE"])


# --- Performance (S1 criterion: build + write <= 1 s) -----------------------------------------


def test_build_and_write_take_less_than_one_second(tmp_path: Path) -> None:
    report = validate_pv_design(load_example())
    assert report.spec is not None
    timings = []
    for run in range(3):
        started = time.perf_counter()
        write_dxf(build_diagram(report.spec, report.derived), tmp_path / f"sld{run}.dxf")
        timings.append(time.perf_counter() - started)
    assert min(timings) <= 1.0, f"build + write took {min(timings):.2f} s"
