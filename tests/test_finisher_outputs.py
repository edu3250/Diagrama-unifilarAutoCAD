"""DWG and PDF inspection without Autodesk or PDF libraries."""

from __future__ import annotations

import zlib
from pathlib import Path

from pvsld.finishers.fake import FAKE_PDF, fake_dwg_bytes
from pvsld.finishers.outputs import dwg_version, find_markings, inspect_dwg, inspect_pdf


def test_dwg_version_reads_the_first_six_bytes() -> None:
    assert dwg_version(b"AC1032\x00\x00") == "AC1032"
    assert dwg_version(b"AC1015") == "AC1015"
    assert dwg_version(b"%PDF-1") is None
    assert dwg_version(b"") is None


def test_inspect_dwg_finds_version_trusted_text_and_product(tmp_path: Path) -> None:
    path = tmp_path / "sld.dwg"
    path.write_bytes(fake_dwg_bytes())
    info = inspect_dwg(path)
    assert info.version == "AC1032"
    assert info.release is not None
    assert info.release.startswith("DWG 2018")
    assert info.trusted
    assert info.trusted_dwg_text is not None
    assert info.trusted_dwg_text.startswith("Autodesk DWG.  This file is a Trusted DWG")
    assert info.trusted_dwg_text.endswith("Autodesk licensed application.")
    assert len(info.product_information) == 1
    assert 'name ="AutoCAD"' in info.product_information[0]
    assert 'registry_localeID="1034"' in info.product_information[0]
    assert len(info.summary_properties) == 1
    assert "<string>AutoCAD 2027</string>" in info.summary_properties[0]
    assert info.markings == ()


def test_a_complete_product_information_element_keeps_its_end(tmp_path: Path) -> None:
    path = tmp_path / "full.dwg"
    element = '<ProductInformation name ="AutoCAD" registry_version="26.0" />'
    path.write_bytes(b"AC1032" + ("\x00" + element + "\x00").encode("utf-16-le"))
    assert inspect_dwg(path).product_information == (element,)


def test_inspect_dwg_without_trusted_text_or_known_version(tmp_path: Path) -> None:
    path = tmp_path / "other.dwg"
    path.write_bytes(fake_dwg_bytes(version=b"AC1099", trusted=False))
    info = inspect_dwg(path)
    assert info.version == "AC1099"
    assert info.release is None
    assert not info.trusted


def test_trusted_text_is_found_at_an_odd_byte_offset(tmp_path: Path) -> None:
    path = tmp_path / "odd.dwg"
    path.write_bytes(b"AC1032" + b"\x01" + "a Trusted DWG file".encode("utf-16-le"))
    assert inspect_dwg(path).trusted


def test_markings_in_ascii_and_utf16() -> None:
    data = b"xx PRODUCED BY AN AUTODESK EDUCATIONAL PRODUCT xx" + "Versión para estudiantes".encode(
        "utf-16-le"
    )
    words = {marking.word for marking in find_markings(data)}
    assert {"educational", "estudiant"} <= words
    assert find_markings(b"plain technical drawing") == []


def test_inspect_pdf_reads_pages_size_producer_and_creator(tmp_path: Path) -> None:
    path = tmp_path / "sld.pdf"
    path.write_bytes(FAKE_PDF)
    info = inspect_pdf(path)
    assert info.header_ok
    assert info.version == "1.6"
    assert info.pages == 1
    assert info.page_sizes_mm == ((420.0, 297.0),)
    assert info.producer == "pdfplot26.hdi 26.0.0 Autodesk"
    assert info.creator == "AutoCAD 2027"
    assert info.markings == ()


def test_inspect_pdf_inflates_streams_and_reads_utf16_and_hex_strings(tmp_path: Path) -> None:
    content = zlib.compress(b"BT (PRODUCED BY AN AUTODESK STUDENT VERSION) Tj ET")
    producer = b"\xfe\xff" + "Autodesk Ñ".encode("utf-16-be")
    data = (
        b"%PDF-1.7\n5 0 obj\n<< /Length 9 /Filter /FlateDecode >>\nstream\n"
        + content
        + b"\nendstream\nendobj\n<< /Producer ("
        + producer
        + b") /Creator <414243> >>\n"
        + b"6 0 obj\n<< /Length 3 >>\nstream\nnot zlib\nendstream\n"
    )
    path = tmp_path / "stamped.pdf"
    path.write_bytes(data)
    info = inspect_pdf(path)
    assert info.streams_inflated == 1
    assert info.producer == "Autodesk Ñ"
    assert info.creator == "ABC"
    assert info.pages == 0
    assert any(m.word == "student" and m.where.startswith("pdf-stream-0") for m in info.markings)


def test_inspect_pdf_reads_xmp_metadata(tmp_path: Path) -> None:
    path = tmp_path / "xmp.pdf"
    path.write_bytes(b"%PDF-1.6\n<pdf:Producer>Plotter X</pdf:Producer><xmp:CreatorTool>")
    assert inspect_pdf(path).producer == "Plotter X"


def test_inspect_pdf_rejects_a_non_pdf(tmp_path: Path) -> None:
    path = tmp_path / "fake.pdf"
    path.write_bytes(b"AC1032 not a pdf")
    info = inspect_pdf(path)
    assert not info.header_ok
    assert info.version is None
    assert info.pages == 0
