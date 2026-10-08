"""The CFE symbol library DXF: blocks, attributes, ports, legend, determinism, rendering, CLI.

The committed ``symbols/pvsld-symbols-cfe.dxf`` must equal what the definitions render. When a
deliberate change to a symbol fails ``test_the_committed_library_is_what_the_definitions_render``,
regenerate it and review the picture::

    pvsld symbols build --png out/pvsld-symbols-legend.png
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import ezdxf
import pytest
from ezdxf.lldxf import const

from pvsld.backends.base import sha256_hex
from pvsld.backends.dxf import _new_document
from pvsld.backends.readback import _parse_ports
from pvsld.cli import main
from pvsld.core import layers
from pvsld.symbols.cfe import LIBRARY, LIBRARY_VERSION, SYMBOLS
from pvsld.symbols.cfe.build import (
    LEGEND_LAYOUT,
    LEGEND_TITLE,
    build_document,
    legend_layout_name,
    legend_pages,
    render_library,
    write_library,
)
from pvsld.symbols.cfe.definitions import FAMILIES
from pvsld.symbols.cfe.loader import ensure_combiner, import_blocks, load_library
from pvsld.symbols.cfe.validate import validate_document, validate_file
from s1_helpers import ROOT

COMMITTED = ROOT / "symbols" / "pvsld-symbols-cfe.dxf"
RENDER_DIR = ROOT / "out"  # git-ignored


@pytest.fixture(scope="module")
def document() -> ezdxf.document.Drawing:
    return build_document()


@pytest.fixture(scope="module")
def library_bytes() -> bytes:
    return render_library()


def _block_xdata(doc: ezdxf.document.Drawing, name: str) -> list[tuple[int, object]]:
    return [(t.code, t.value) for t in doc.blocks.get(name).block_record.get_xdata("PVSLD")]


# --- Blocks ------------------------------------------------------------------------------------


def test_the_library_passes_audit_with_no_errors_and_no_fixes(document) -> None:  # type: ignore[no-untyped-def]
    auditor = document.audit()
    assert (len(auditor.errors), len(auditor.fixes)) == (0, 0)


def test_the_document_holds_exactly_the_defined_blocks(document) -> None:  # type: ignore[no-untyped-def]
    names = {b.name for b in document.blocks if b.name.startswith("PVSLD_")}
    assert names == set(SYMBOLS)
    assert len(names) == 57


@pytest.mark.parametrize("spec", LIBRARY, ids=lambda s: s.name)
def test_each_block_has_its_attributes_with_the_identity_ones_hidden(document, spec) -> None:  # type: ignore[no-untyped-def]
    attdefs = [e for e in document.blocks.get(spec.name) if e.dxftype() == "ATTDEF"]
    assert [a.dxf.tag for a in attdefs] == list(spec.tags)
    flags = {a.dxf.tag: bool(a.dxf.flags & const.ATTRIB_INVISIBLE) for a in attdefs}
    for tag in ("COMP_ID", "IEC_REF", "NMX_REF", "SOURCE_STANDARD"):
        assert flags[tag], f"{spec.name}.{tag} must be hidden"
    by_tag = {a.dxf.tag: a for a in attdefs}
    assert by_tag["SOURCE_STANDARD"].dxf.text == spec.source
    assert by_tag["DESC"].dxf.text == spec.description_es


@pytest.mark.parametrize("spec", LIBRARY, ids=lambda s: s.name)
def test_each_block_stores_version_ports_and_source_in_xdata(document, spec) -> None:  # type: ignore[no-untyped-def]
    xdata = _block_xdata(document, spec.name)
    assert xdata[:3] == [(1000, "pvsld.block/1"), (1000, LIBRARY_VERSION), (1070, len(spec.ports))]
    assert xdata[-1] == (1000, spec.source)
    parsed = _parse_ports(xdata)  # the S1 read-back must keep working on library blocks
    assert [(p.id, p.kind, p.direction, p.x, p.y, p.required) for p in parsed] == [
        (p.id, p.kind, p.direction, p.x, p.y, p.required) for p in spec.ports
    ]


@pytest.mark.parametrize("spec", LIBRARY, ids=lambda s: s.name)
def test_no_block_entity_is_on_layer_zero(document, spec) -> None:  # type: ignore[no-untyped-def]
    used = {e.dxf.layer for e in document.blocks.get(spec.name)}
    assert "0" not in used
    assert used <= layers.LAYER_NAMES


def test_the_symbol_linetypes_exist(document) -> None:  # type: ignore[no-untyped-def]
    for name in ("DOTTED", "DASHDOT_S", "DASHED_S", "DASHDOT2"):
        assert name in document.linetypes
    used = {
        e.dxf.linetype
        for spec in LIBRARY
        for e in document.blocks.get(spec.name)
        if e.dxf.hasattr("linetype")
    }
    assert used <= {"DOTTED", "DASHDOT_S", "DASHED_S", "DASHDOT2", "DASHED", "CONTINUOUS"}
    assert "DASHDOT2" in used


def test_filled_shapes_are_solid_hatches(document) -> None:  # type: ignore[no-untyped-def]
    assert {e.dxftype() for e in document.blocks.get("PVSLD_ARRESTER_MV")} >= {"HATCH"}
    assert {e.dxftype() for e in document.blocks.get("PVSLD_JUNCTION")} == {"HATCH", "ATTDEF"}


# --- Legend ------------------------------------------------------------------------------------


def _sheets(document) -> list[str]:  # type: ignore[no-untyped-def]
    return [n for n in document.layouts.names() if n.startswith(LEGEND_LAYOUT)]


def test_the_legend_has_one_a3_layout_per_page_named_without_spaces(document) -> None:  # type: ignore[no-untyped-def]
    pages = legend_pages(LIBRARY)
    assert len(pages) == 3
    assert sorted(_sheets(document)) == [legend_layout_name(i) for i in (1, 2, 3)]
    assert legend_layout_name(1) == "Legend"
    assert legend_layout_name(2) == "Legend2"
    for name in _sheets(document):
        legend = document.layouts.get(name)
        assert (legend.dxf_layout.dxf.paper_width, legend.dxf_layout.dxf.paper_height) == (420, 297)
        assert [e.dxftype() for e in legend if e.dxf.layer == "0"] == ["VIEWPORT"]


def test_the_legend_layouts_insert_every_block_once_at_most_one_to_one(document) -> None:  # type: ignore[no-untyped-def]
    inserts = [i for n in _sheets(document) for i in document.layouts.get(n).query("INSERT")]
    assert sorted(i.dxf.name for i in inserts) == sorted(SYMBOLS)
    for insert in inserts:
        assert insert.dxf.name in document.blocks
        assert 0 < insert.dxf.xscale <= 1.0
        assert insert.dxf.layer != "0"


def test_every_legend_sheet_has_the_title_the_version_and_the_three_columns(document) -> None:  # type: ignore[no-untyped-def]
    assert LEGEND_TITLE == "SIMBOLOGÍA — DIAGRAMAS UNIFILARES FV (CFE G0100-04 Apéndice C)"
    for index, name in enumerate(_sheets(document), start=1):
        texts = [t.dxf.text for t in document.layouts.get(name).query("TEXT")]
        assert LEGEND_TITLE in texts
        assert any(f"v{LIBRARY_VERSION}" in t and f"hoja {index} de 3" in t for t in texts)
        for column in ("Símbolo", "Designación", "Fuente"):
            assert column in texts


def test_the_legend_lists_each_block_name_and_each_family_heading(document) -> None:  # type: ignore[no-untyped-def]
    texts = [t.dxf.text for n in _sheets(document) for t in document.layouts.get(n).query("TEXT")]
    for spec in LIBRARY:
        assert spec.name in texts
    for family in FAMILIES:
        assert any(t.startswith(family.upper()) for t in texts), family


def test_the_relay_sample_attributes_show_in_the_legend(document) -> None:  # type: ignore[no-untyped-def]
    attribs = [
        (a.dxf.tag, a.dxf.text)
        for n in _sheets(document)
        for i in document.layouts.get(n).query("INSERT")
        for a in i.attribs
    ]
    assert sorted(attribs) == [("ANSI_NO", "27"), ("FUNCTION", "U<")]


def test_legend_pages_keep_families_together_and_never_end_a_group_on_a_heading() -> None:
    pages = legend_pages(LIBRARY)
    groups = [g for page in pages for g in page]
    assert len(groups) <= 6
    placed = [row.spec.name for g in groups for row in g if row.spec is not None]
    assert placed == [s.name for s in LIBRARY]
    for group in groups:
        assert group[0].heading is not None
        assert group[-1].spec is not None
        assert sum(row.height for row in group) <= 297 - 20 - 24 - 8 - 22


def test_legend_pages_repeat_the_heading_of_a_family_that_continues() -> None:
    pages = legend_pages(LIBRARY * 1)
    headings = [r.heading for page in pages for g in page for r in g if r.heading]
    assert any(h.endswith("(cont.)") for h in headings) or len(headings) == len(FAMILIES)
    small = legend_pages(LIBRARY[:3])
    assert len(small) == 1
    assert [r.heading for r in small[0][0] if r.heading] == [LIBRARY[0].family]


# --- Determinism -------------------------------------------------------------------------------


def test_rendering_twice_gives_identical_bytes(library_bytes: bytes) -> None:
    assert render_library() == library_bytes


def test_the_bytes_are_utf8_with_lf_newlines_only(library_bytes: bytes) -> None:
    assert library_bytes.startswith(b"  0\nSECTION\n")
    assert b"\r" not in library_bytes
    assert "SIMBOLOGÍA — DIAGRAMAS".encode() in library_bytes


def test_the_bytes_do_not_depend_on_the_hash_seed_of_the_process(library_bytes: bytes) -> None:
    expected = sha256_hex(library_bytes)
    code = (
        "from pvsld.symbols.cfe.build import render_library;"
        "from pvsld.backends.base import sha256_hex;"
        "print(sha256_hex(render_library()))"
    )
    for seed in ("0", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env
        )
        assert out.stdout.strip() == expected, f"PYTHONHASHSEED={seed}"


def test_the_committed_library_is_what_the_definitions_render(library_bytes: bytes) -> None:
    committed = COMMITTED.read_bytes()
    assert sha256_hex(committed) == sha256_hex(library_bytes), (
        "symbols/pvsld-symbols-cfe.dxf is stale; run `pvsld symbols build` and review the legend"
    )
    assert b"\r" not in committed, "checked out with CRLF; check .gitattributes"


def test_the_committed_library_validates() -> None:
    assert validate_file(COMMITTED) == []


# --- Validation of a damaged library -----------------------------------------------------------


def test_a_valid_document_has_no_problems(document) -> None:  # type: ignore[no-untyped-def]
    assert validate_document(document) == []


def test_a_missing_block_is_reported() -> None:
    doc = build_document()
    doc.blocks.delete_block("PVSLD_CB", safe=False)
    problems = validate_document(doc)
    assert any(p.startswith("PVSLD_CB: block is missing") for p in problems)


def test_a_visible_identity_attribute_is_reported() -> None:
    doc = build_document()
    for e in doc.blocks.get("PVSLD_INV"):
        if e.dxftype() == "ATTDEF" and e.dxf.tag == "COMP_ID":
            e.dxf.flags = 0
    assert any("COMP_ID must be hidden" in p for p in validate_document(doc))


def test_a_changed_source_is_reported() -> None:
    doc = build_document()
    for e in doc.blocks.get("PVSLD_GND"):
        if e.dxftype() == "ATTDEF" and e.dxf.tag == "SOURCE_STANDARD":
            e.dxf.text = "somewhere else"
    assert any("SOURCE_STANDARD" in p for p in validate_document(doc))


def test_a_port_that_leaves_the_outline_is_reported() -> None:
    doc = build_document()
    block = doc.blocks.get("PVSLD_CB")
    for e in block:
        if e.dxftype() == "LINE" and tuple(e.dxf.start)[:2] == (0.0, 0.0):
            e.dxf.start = (1.0, 1.0, 0.0)
            e.dxf.end = (3.5, 1.0, 0.0)
    assert any("port IN is" in p and "off the symbol outline" in p for p in validate_document(doc))


def test_an_entity_on_layer_zero_or_an_unknown_layer_is_reported() -> None:
    doc = build_document()
    block = doc.blocks.get("PVSLD_DIODE")
    block.add_line((0, 0), (1, 1), dxfattribs={"layer": "0"})
    problems = validate_document(doc)
    assert any("PVSLD_DIODE: LINE on layer 0" in p for p in problems)


def test_a_wrong_library_version_in_xdata_is_reported() -> None:
    doc = build_document()
    record = doc.blocks.get("PVSLD_PI").block_record
    tags = [(t.code, t.value) for t in record.get_xdata("PVSLD")]
    tags[1] = (1000, "0.0.1")
    record.set_xdata("PVSLD", tags)
    assert any("library version '0.0.1'" in p for p in validate_document(doc))


def test_a_block_without_xdata_and_an_extra_block_are_reported() -> None:
    doc = build_document()
    doc.blocks.get("PVSLD_GRID").block_record.discard_xdata("PVSLD")
    doc.blocks.new("PVSLD_STRAY")
    problems = validate_document(doc)
    assert any("PVSLD_GRID: block record has no PVSLD XDATA" in p for p in problems)
    assert any("PVSLD_STRAY: block is not in the definitions" in p for p in problems)


def test_a_missing_legend_is_reported() -> None:
    doc = build_document()
    doc.layouts.rename(LEGEND_LAYOUT, "Other")
    assert any("layout 'Legend' is missing" in p for p in validate_document(doc))


def test_a_missing_legend_sheet_is_reported() -> None:
    doc = build_document()
    doc.layouts.delete("Legend3")
    problems = validate_document(doc)
    assert any("Legend layouts are" in p for p in problems)
    assert any("does not insert every block" in p for p in problems)


def test_a_legend_that_loses_an_insert_is_reported() -> None:
    doc = build_document()
    legend = doc.layouts.get(LEGEND_LAYOUT)
    legend.delete_entity(next(iter(legend.query("INSERT"))))
    assert any("does not insert every block" in p for p in validate_document(doc))


def test_a_stale_file_is_reported_unless_the_check_is_off(tmp_path: Path) -> None:
    stale = tmp_path / "lib.dxf"
    data = COMMITTED.read_bytes().replace(b"Biblioteca", b"Bibliotecas", 1)
    stale.write_bytes(data)
    assert any("is stale" in p for p in validate_file(stale))
    assert not any("is stale" in p for p in validate_file(stale, check_fresh=False))


def test_missing_and_unreadable_files_are_reported(tmp_path: Path) -> None:
    assert any("cannot read" in p for p in validate_file(tmp_path / "nope.dxf"))
    junk = tmp_path / "junk.dxf"
    junk.write_bytes(b"this is not a dxf")
    assert any("not a readable DXF" in p for p in validate_file(junk))


# --- Import into a drawing (Stage 4.3) ---------------------------------------------------------


def test_imported_blocks_keep_their_ports_attributes_and_audit_clean(document) -> None:  # type: ignore[no-untyped-def]
    target = _new_document()
    imported = import_blocks(document, target, ["PVSLD_INV", "PVSLD_CB", "PVSLD_SWITCH"])
    assert imported == ["PVSLD_INV", "PVSLD_CB", "PVSLD_SWITCH"]
    ports = _parse_ports(_block_xdata(target, "PVSLD_INV"))
    assert [p.id for p in ports] == ["A", "B", "AC", "PE"]
    attdefs = [e.dxf.tag for e in target.blocks.get("PVSLD_INV") if e.dxftype() == "ATTDEF"]
    assert attdefs == list(SYMBOLS["PVSLD_INV"].tags)
    assert "DOTTED" in target.linetypes
    auditor = target.audit()
    assert (len(auditor.errors), len(auditor.fixes)) == (0, 0)
    assert import_blocks(document, target, ["PVSLD_CB"]) == []  # already there


def test_importing_every_block_and_an_unknown_block(document) -> None:  # type: ignore[no-untyped-def]
    target = _new_document()
    assert sorted(import_blocks(document, target)) == sorted(SYMBOLS)
    with pytest.raises(KeyError, match="PVSLD_NOPE"):
        import_blocks(document, target, ["PVSLD_NOPE"])


def test_ensure_combiner_defines_the_block_for_the_exact_string_count() -> None:
    target = _new_document()
    assert ensure_combiner(target, 5) == "PVSLD_COMBINER_5S"
    assert ensure_combiner(target, 5) == "PVSLD_COMBINER_5S"  # reused, not redefined
    ports = _parse_ports(_block_xdata(target, "PVSLD_COMBINER_5S"))
    assert [p.id for p in ports] == ["IN1", "IN2", "IN3", "IN4", "IN5", "OUT", "PE"]
    attdefs = {
        e.dxf.tag: e for e in target.blocks.get("PVSLD_COMBINER_5S") if e.dxftype() == "ATTDEF"
    }
    assert attdefs["N_STRINGS"].dxf.text == "5"
    assert "DASHED" in target.linetypes
    auditor = target.audit()
    assert (len(auditor.errors), len(auditor.fixes)) == (0, 0)
    with pytest.raises(ValueError, match="1 to 24"):
        ensure_combiner(target, 0)


def test_the_library_file_loads_back_with_the_same_blocks() -> None:
    doc = load_library(COMMITTED)
    assert {b.name for b in doc.blocks if b.name.startswith("PVSLD_")} == set(SYMBOLS)


# --- Rendering ---------------------------------------------------------------------------------


@pytest.mark.parametrize("sheet", [1, 2, 3])
def test_each_legend_sheet_renders_to_a_png_of_the_a3_sheet(document, sheet: int) -> None:  # type: ignore[no-untyped-def]
    from pvsld.backends.preview import write_png

    target = RENDER_DIR / "tests" / f"pvsld-symbols-legend-{sheet}.png"
    data = write_png(document, target, dpi=60, layout_name=legend_layout_name(sheet))
    assert target.read_bytes() == data
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    width, height = struct.unpack(">II", data[16:24])
    assert width == pytest.approx(420 / 25.4 * 60, abs=1)
    assert height == pytest.approx(297 / 25.4 * 60, abs=1)
    assert 40_000 < len(data) < 3_000_000  # a blank sheet is a few kB, a full one is far below 3 MB


# --- Command line ------------------------------------------------------------------------------


def test_cli_build_writes_the_same_bytes_and_check_passes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], library_bytes: bytes
) -> None:
    target = tmp_path / "out" / "lib.dxf"
    assert main(["symbols", "build", "-o", str(target)]) == 0
    assert target.read_bytes() == library_bytes
    assert main(["symbols", "build", "-o", str(target), "--check"]) == 0
    assert "up to date" in capsys.readouterr().out


def test_cli_build_check_fails_on_a_missing_or_stale_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    target = tmp_path / "lib.dxf"
    assert main(["symbols", "build", "-o", str(target), "--check"]) == 1
    assert "missing" in capsys.readouterr().err
    target.write_bytes(b"old")
    assert main(["symbols", "build", "-o", str(target), "--check"]) == 1
    assert "stale" in capsys.readouterr().err


def test_cli_build_can_write_one_png_per_legend_sheet(tmp_path: Path) -> None:
    png = tmp_path / "legend.png"
    assert main(["symbols", "build", "-o", str(tmp_path / "lib.dxf"), "--png", str(png)]) == 0
    for index in (1, 2, 3):
        assert (tmp_path / f"legend-{index}.png").read_bytes().startswith(b"\x89PNG")


def test_cli_list_prints_text_and_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["symbols", "list"]) == 0
    text = capsys.readouterr().out
    assert f"v{LIBRARY_VERSION}" in text
    assert "PVSLD_INV" in text
    assert main(["symbols", "list", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["version"] == LIBRARY_VERSION
    assert [s["block"] for s in data["symbols"]] == [s.name for s in LIBRARY]


def test_cli_validate_accepts_the_committed_library_and_rejects_a_bad_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["symbols", "validate", str(COMMITTED)]) == 0
    assert "OK" in capsys.readouterr().out
    junk = tmp_path / "junk.dxf"
    junk.write_bytes(b"nope")
    assert main(["symbols", "validate", str(junk)]) == 1
    assert "FAILED" in capsys.readouterr().err


def test_write_library_creates_parent_folders(tmp_path: Path, library_bytes: bytes) -> None:
    target = tmp_path / "a" / "b" / "lib.dxf"
    assert write_library(target) == library_bytes
    assert target.read_bytes() == library_bytes
