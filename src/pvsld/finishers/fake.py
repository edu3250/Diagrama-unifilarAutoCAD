"""A fake ``accoreconsole.exe`` runner for tests without AutoCAD (CI, the MCP server's tests).

:class:`FakeCoreConsole` is a :data:`~pvsld.finishers.core_console.Runner`: it reads the script the
finisher wrote, then prints what Core Console would print (UTF-16LE, script echo, markers, an AUDIT
summary) and writes a DWG and a PDF that pass the finisher's checks. Each knob breaks one thing, so
a test can prove the finisher reports that failure instead of a silent success.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from pvsld.finishers.core_console import STEP_ORDER, ProcessOutcome

__all__ = ["FAKE_PDF", "FakeCoreConsole", "fake_dwg_bytes"]

TRUSTED_SENTENCE = (
    "Autodesk DWG.  This file is a Trusted DWG last saved by an Autodesk application or Autodesk "
    "licensed application."
)
PRODUCT_INFORMATION = (
    '<ProductInformation name ="AutoCAD" build_version="X.118.0.0(x64)" registry_version="26.0" '
    'install_id_string="pvsld" registry_localeID="1034" git_commit_id="0123456789abcdef'
)
SUMMARY_PROPERTIES = (
    '<prop_set fmt_id="{f29f85e0-4ff9-1068-ab91-08002b27b3d9}"><prop id="8"><string>user</string>'
    '</prop><prop id="258"><string>AutoCAD 2027</string></prop></prop_set>'
)
FAKE_PDF = (
    b"%PDF-1.6\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 1190.55 841.89] >>\nendobj\n"
    b"4 0 obj\n<< /Producer (pdfplot26.hdi 26.0.0 Autodesk) /Creator (AutoCAD 2027) >>\nendobj\n"
    b"trailer\n<< /Root 1 0 R /Info 4 0 R >>\n%%EOF\n"
)


def fake_dwg_bytes(version: bytes = b"AC1032", trusted: bool = True) -> bytes:
    """A stand-in DWG: the version string, padding and the UTF-16LE provenance text."""
    parts = ["AppInfoDataList", "r" + TRUSTED_SENTENCE if trusted else "", PRODUCT_INFORMATION]
    body = "\x00".join([*parts, SUMMARY_PROPERTIES, ""])
    return version + b"\x00" * 122 + body.encode("utf-16-le") + b"\x00" * 64


def _unquote(line: str) -> str:
    return line[1:-1] if len(line) > 1 and line[0] == line[-1] == '"' else line


@dataclass
class FakeCoreConsole:
    """Simulates one Core Console run per call; the defaults behave like a healthy run."""

    steps: Sequence[str] = STEP_ORDER
    audit_line: str | None = "Total errors found 0 fixed 0"
    entities: int = 274
    layouts: str = "A3|"
    write_dwg: bool = True
    write_pdf: bool = True
    dwg_version: bytes = b"AC1032"
    trusted: bool = True
    exit_code: int | None = 0
    timed_out: bool = False
    silent: bool = False
    extra_lines: Sequence[str] = ()
    duration_s: float = 4.2
    clock_ms: float = 36_000_000.0
    calls: list[list[str]] = field(default_factory=list)

    def __call__(
        self, command: Sequence[str], cwd: Path, timeout_s: float, raw_output: Path
    ) -> ProcessOutcome:
        self.calls.append(list(command))
        script = Path(command[list(command).index("/s") + 1]).read_bytes().decode("ascii")
        lines = script.split("\r\n")
        if not self.silent:
            self._write_outputs(lines)
        output = b"" if self.silent else self._console_text(lines).encode("utf-16-le")
        raw_output.write_bytes(output)
        return ProcessOutcome(
            exit_code=None if self.timed_out else self.exit_code,
            output=output,
            timed_out=self.timed_out,
            duration_s=self.duration_s,
            pid=4242,
        )

    def _write_outputs(self, lines: list[str]) -> None:
        if self.write_dwg and "_.SAVEAS" in lines:
            target = Path(_unquote(lines[lines.index("_.SAVEAS") + 2]))
            target.write_bytes(fake_dwg_bytes(self.dwg_version, self.trusted))
        if self.write_pdf and "_.-PLOT" in lines:
            start = lines.index("_.-PLOT")
            pdf = next(_unquote(x) for x in lines[start:] if _unquote(x).lower().endswith(".pdf"))
            Path(pdf).write_bytes(FAKE_PDF)

    def _console_text(self, lines: list[str]) -> str:
        out = [
            "Redirect stdout (if specified) to a file for faster performance.",
            "AutoCAD Core Engine Console - Copyright 2026 Autodesk, Inc.  All rights reserved.",
        ]
        clock = self.clock_ms
        printed = set()
        for line in lines:
            out.append(f"Command: {line}")  # the echo of each script line
            for name in STEP_ORDER:
                if f":STEP:{name}:" in line and name in self.steps and name not in printed:
                    if name == "audited" and self.audit_line is not None:
                        out += ["Auditing Header", "Auditing Tables", self.audit_line]
                    printed.add(name)
                    clock += 250.0
                    out.append(f"PVSLD:STEP:{name}:{clock:.0f}")
            if ":CHECK:entities:" in line and "loaded" in self.steps:
                out.append(f"PVSLD:CHECK:entities:{self.entities}")
            if ":CHECK:layouts:" in line and "loaded" in self.steps:
                out.append(f"PVSLD:CHECK:layouts:{self.layouts}")
        out += list(self.extra_lines)
        return "\r\n".join(out) + "\r\n"
