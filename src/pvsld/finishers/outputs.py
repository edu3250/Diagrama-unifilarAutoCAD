"""Inspect what a finisher wrote: the DWG version and provenance text, and the PDF basics.

A successful exit code is not evidence (ADR-0001): the finisher checks the files themselves.

* DWG: the six-byte version string (``AC1032`` is "DWG 2018", written by AutoCAD 2018 to 2027) and
  the plain text AutoCAD stores uncompressed (UTF-16LE) in the file: the TrustedDWG sentence, the
  ``<ProductInformation .../>`` element and the DWGPROPS ``<prop_set>`` (which includes the Windows
  login name as "last saved by").
* PDF: header, page count, page size (MediaBox, in mm), producer and creator, read from the raw
  bytes and from every Flate stream that inflates.

Both are scanned for educational or non-commercial wording in ASCII/Latin-1 and UTF-16LE, because
the owner's AutoCAD runs on an Education licence. Glyph-encoded PDF text and vector-drawn stamps
cannot be found this way; the spike report says how the PDF was also checked by eye.
"""

from __future__ import annotations

import re
import zlib
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "DWG_RELEASES",
    "MARKING_WORDS",
    "DwgInfo",
    "Marking",
    "PdfInfo",
    "dwg_version",
    "find_markings",
    "inspect_dwg",
    "inspect_pdf",
]

DWG_RELEASES = {
    "AC1032": "DWG 2018 (AutoCAD 2018-2027)",
    "AC1027": "DWG 2013 (AutoCAD 2013-2017)",
    "AC1024": "DWG 2010 (AutoCAD 2010-2012)",
    "AC1021": "DWG 2007 (AutoCAD 2007-2009)",
    "AC1018": "DWG 2004 (AutoCAD 2004-2006)",
    "AC1015": "DWG 2000 (AutoCAD 2000-2002)",
}
TRUSTED_DWG_TEXT = "Trusted DWG"
MARKING_WORDS = (
    "educational",
    "education",
    "educación",
    "educacion",
    "educativ",
    "student",
    "estudiant",
    "academic",
    "académic",
    "no comercial",
    "non-commercial",
    "noncommercial",
    "not for commercial",
    "uso no comercial",
)
# AutoCAD stores the element with a length cap, so it can end without "/>" (S4: AutoCAD 2027).
_PRODUCT_INFO = re.compile(r"<ProductInformation\b[ -;=?-~]{0,400}>?")
# The DWGPROPS summary (dates, "last saved by" login name, application) as an XML property set.
_SUMMARY_INFO = re.compile(r"<prop_set\b[ -~]{0,2000}?</prop_set>")
_POINTS_PER_MM = 72 / 25.4


@dataclass(frozen=True)
class Marking:
    """A marking word found in a file: which word, in which encoding/stream, and its context."""

    word: str
    where: str
    context: str


@dataclass(frozen=True)
class DwgInfo:
    """Facts read from a DWG file without an Autodesk library."""

    path: Path
    size_bytes: int
    version: str | None
    release: str | None
    trusted_dwg_text: str | None
    product_information: tuple[str, ...]
    summary_properties: tuple[str, ...]
    markings: tuple[Marking, ...]

    @property
    def trusted(self) -> bool:
        """``True`` when the TrustedDWG sentence ("... last saved by an Autodesk application") is
        present in the file."""
        return self.trusted_dwg_text is not None


@dataclass(frozen=True)
class PdfInfo:
    """Facts read from a PDF file without a PDF library."""

    path: Path
    size_bytes: int
    header_ok: bool
    version: str | None
    pages: int
    page_sizes_mm: tuple[tuple[float, float], ...]
    producer: str | None
    creator: str | None
    streams_inflated: int
    markings: tuple[Marking, ...]


def dwg_version(data: bytes) -> str | None:
    """The DWG version string (``AC1032`` ...) from the first six bytes, or ``None``."""
    head = data[:6]
    return head.decode("ascii") if re.fullmatch(rb"AC10\d\d", head) else None


def _texts(data: bytes, label: str) -> Iterable[tuple[str, str]]:
    """``data`` decoded as Latin-1 and as UTF-16LE at both byte alignments."""
    yield f"{label}/latin-1", data.decode("latin-1")
    for offset in (0, 1):
        chunk = data[offset:]
        chunk = chunk[: len(chunk) - len(chunk) % 2]
        yield f"{label}/utf-16le", chunk.decode("utf-16-le", errors="replace")


def find_markings(
    data: bytes, words: Sequence[str] = MARKING_WORDS, label: str = "file"
) -> list[Marking]:
    """Each occurrence of ``words`` (case-insensitive) in ``data``, with 40 characters around."""
    found: list[Marking] = []
    seen: set[tuple[str, str]] = set()
    for where, text in _texts(data, label):
        lowered = text.lower()
        for word in words:
            start = lowered.find(word.lower())
            while start != -1:
                context = text[max(0, start - 40) : start + len(word) + 40]
                context = "".join(ch if ch.isprintable() else "." for ch in context)
                key = (word, context)
                if key not in seen:
                    seen.add(key)
                    found.append(Marking(word, where, context))
                start = lowered.find(word.lower(), start + 1)
    return found


def _utf16_texts(data: bytes) -> list[str]:
    return [text for where, text in _texts(data, "dwg") if where.endswith("utf-16le")]


def _ascii_run_around(text: str, index: int) -> str:
    """The run of printable ASCII characters that contains ``text[index]``."""
    start = index
    while start > 0 and " " <= text[start - 1] <= "~":
        start -= 1
    end = index
    while end < len(text) and " " <= text[end] <= "~":
        end += 1
    return text[start:end].strip()


def _trusted_sentence(texts: Sequence[str]) -> str | None:
    """The TrustedDWG sentence, from "Autodesk DWG." when present (a length byte precedes it)."""
    for text in texts:
        index = text.find(TRUSTED_DWG_TEXT)
        if index != -1:
            sentence = _ascii_run_around(text, index)
            start = sentence.find("Autodesk DWG")
            return sentence[start:] if start != -1 else sentence
    return None


def _unique_matches(pattern: re.Pattern[str], texts: Sequence[str]) -> tuple[str, ...]:
    found: list[str] = []
    for text in texts:
        for match in pattern.finditer(text):
            if match.group(0) not in found:
                found.append(match.group(0))
    return tuple(found)


def inspect_dwg(path: Path) -> DwgInfo:
    """Read the version, the TrustedDWG sentence, product information and markings of a DWG."""
    data = path.read_bytes()
    version = dwg_version(data)
    texts = _utf16_texts(data)
    return DwgInfo(
        path=path,
        size_bytes=len(data),
        version=version,
        release=DWG_RELEASES.get(version or ""),
        trusted_dwg_text=_trusted_sentence(texts),
        product_information=_unique_matches(_PRODUCT_INFO, texts),
        summary_properties=_unique_matches(_SUMMARY_INFO, texts),
        markings=tuple(find_markings(data, label="dwg")),
    )


def _inflated_streams(data: bytes) -> list[bytes]:
    streams: list[bytes] = []
    for match in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.DOTALL):
        try:
            streams.append(zlib.decompress(match.group(1)))
        except zlib.error:
            continue
    return streams


def _pdf_string(raw: bytes) -> str:
    if raw.startswith(b"\xfe\xff"):
        return raw[2:].decode("utf-16-be", errors="replace")
    return raw.decode("latin-1")


def _info_value(sources: Sequence[bytes], key: bytes) -> str | None:
    for source in sources:
        literal = re.search(rb"/" + key + rb"\s*\((.*?)(?<!\\)\)", source, re.DOTALL)
        if literal:
            return _pdf_string(literal.group(1))
        hexa = re.search(rb"/" + key + rb"\s*<([0-9A-Fa-f\s]+)>", source)
        if hexa:
            return _pdf_string(bytes.fromhex(hexa.group(1).decode("ascii")))
        xmp = re.search(rb"<(?:pdf|xmp):" + key + rb">(.*?)</", source, re.DOTALL)
        if xmp:
            return xmp.group(1).decode("utf-8", errors="replace")
    return None


def _page_sizes(sources: Sequence[bytes]) -> tuple[tuple[float, float], ...]:
    sizes: list[tuple[float, float]] = []
    number = rb"(-?\d+(?:\.\d+)?)"
    pattern = re.compile(rb"/MediaBox\s*\[\s*" + rb"\s+".join([number] * 4) + rb"\s*\]")
    for source in sources:
        for match in pattern.finditer(source):
            x0, y0, x1, y1 = (float(value) for value in match.groups())
            sizes.append(
                (round((x1 - x0) / _POINTS_PER_MM, 1), round((y1 - y0) / _POINTS_PER_MM, 1))
            )
    return tuple(sizes)


def inspect_pdf(path: Path) -> PdfInfo:
    """Read the header, pages, page sizes, producer, creator and markings of a PDF."""
    data = path.read_bytes()
    header = re.match(rb"%PDF-(\d\.\d)", data)
    streams = _inflated_streams(data)
    sources = [data, *streams]
    pages = sum(len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", source)) for source in sources)
    markings = find_markings(data, label="pdf")
    for index, stream in enumerate(streams):
        markings += find_markings(stream, label=f"pdf-stream-{index}")
    return PdfInfo(
        path=path,
        size_bytes=len(data),
        header_ok=header is not None,
        version=header.group(1).decode("ascii") if header else None,
        pages=pages,
        page_sizes_mm=_page_sizes(sources),
        producer=_info_value(sources, b"Producer"),
        creator=_info_value(sources, b"Creator"),
        streams_inflated=len(streams),
        markings=tuple(markings),
    )
