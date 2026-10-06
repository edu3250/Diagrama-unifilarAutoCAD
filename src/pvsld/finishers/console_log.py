"""Read what ``accoreconsole.exe`` printed: decode it, then extract progress, AUDIT and problems.

The Core Console prints the echo of every script line, the command prompts and the command output
in the language of the AutoCAD install (Spanish on the reference workstation). Nothing here relies
on the prompts: progress is proven by *markers* that the finisher's script prints through AutoLISP,
and the markers are built at run time (``"PVSLD" ":STEP:"``), so the echo of the script line never
matches the marker pattern; only the evaluated output does.

* ``PVSLD:STEP:<name>:<clock>``: a step finished; ``clock`` is AutoCAD's ``MILLISECS`` (ms since
  Windows started).
* ``PVSLD:CHECK:<key>:<value>``: a fact about the open drawing (entity count, layouts, version).

The AUDIT summary and the problem phrases are the only language-dependent parts; both are matched
in English and Spanish and are bounded by the markers (see :func:`parse_console_log`).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

__all__ = [
    "AuditCounts",
    "ConsoleLog",
    "StepMark",
    "decode_console_output",
    "parse_console_log",
]

MARKER = "PVSLD"
_STEP = re.compile(rf"{MARKER}:STEP:([A-Za-z_]+):(-?\d+(?:\.\d+)?)")
_CHECK = re.compile(rf"{MARKER}:CHECK:([A-Za-z_]+):([^\n]*)")

# "Total errors found 0 fixed 0" (English); the Spanish build words it differently, so any line
# that starts with "Total" and carries exactly two counts is accepted inside the AUDIT region.
_AUDIT_TOTAL = re.compile(
    r"^[ \t]*Total\b[^\d\n]*(\d+)[^\d\n]+(\d+)[^\d\n]*$", re.IGNORECASE | re.M
)

# Phrases that mean a step failed, in English and Spanish (case-insensitive substrings or regexes).
_PROBLEM_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"unknown command|comando desconocido",
        r"invalid or incomplete dxf|drawing discarded|dibujo descartado|entrada dxf no v[aá]lida",
        r"is not a valid (?:dxf|dwg)|no es un archivo (?:dxf|dwg) v[aá]lido",
        r"error in (?:the )?drawing header|error en el encabezamiento",
        r"something went wrong|errorstatus=",  # Core Console's own exit message
        r"^<.*> (?:not found|no encontrad[oa])",  # a rejected prompt answer: script out of step
        r";\s*error\s*:",  # AutoLISP error
        r"^\s*\*\s*(?:invalid|no v[aá]lid)",  # "*Invalid selection*", "*No válido*"
        r"unable to|no se puede|no se ha podido|imposible (?:abrir|guardar|trazar|cargar)",
        r"\bfailed\b|\bfall[oó]\b|ha fallado|error al ",
        r"fatal error|error grave|error fatal",
        r"unhandled exception|excepci[oó]n no (?:controlada|tratada)",
        r"plot(?:ting)? (?:cancel|fail|error)|trazado cancelado|error de trazado",
        r"file not found|archivo no encontrado|no se (?:ha )?encontrado|no se encuentra",
        r"access denied|acceso denegado",
        # TrustedDWG notice when a drawing was last saved by a non-Autodesk application.
        r"not (?:developed|saved|licensed)(?: or licensed)? by (?:an )?autodesk",
        r"no (?:ha sido )?(?:desarrollad|guardad)\w* (?:ni|por|con)\b.*autodesk",
        # Licensing; a plain "licence" or "no comercial" banner line is not a problem.
        r"licen[cs]e? (?:not found|expired|invalid|unavailable|error|check ?out failed)",
        r"no (?:valid )?licen[cs]e|unable to (?:obtain|acquire|check out) (?:a )?licen[cs]e",
        r"licencia (?:no v[aá]lida|caducada|vencida|no disponible|no encontrada)",
        r"no (?:hay|se (?:pudo|ha podido) obtener|se encontr[oó]) (?:una |ninguna )?licencia",
        r"error de licencia",
    )
)
_MAX_PROBLEMS = 20


@dataclass(frozen=True)
class StepMark:
    """A ``PVSLD:STEP`` marker: the script reached ``name`` at ``clock_ms`` (AutoCAD MILLISECS)."""

    name: str
    clock_ms: float
    position: int


@dataclass(frozen=True)
class AuditCounts:
    """The AUDIT summary line: errors found and errors fixed."""

    errors_found: int
    errors_fixed: int
    line: str


@dataclass(frozen=True)
class ConsoleLog:
    """What a Core Console run printed, reduced to the facts the finisher needs."""

    text: str
    steps: tuple[StepMark, ...] = ()
    checks: dict[str, str] = field(default_factory=dict)
    audit: AuditCounts | None = None
    problems: tuple[str, ...] = ()

    def step(self, name: str) -> StepMark | None:
        """The first marker called ``name``, or ``None`` when the script never got there."""
        return next((mark for mark in self.steps if mark.name == name), None)

    def step_durations_ms(self) -> dict[str, float]:
        """Milliseconds between consecutive markers, keyed by the marker that closes the step.

        A negative difference (the 32-bit counter wrapped) is dropped rather than reported.
        """
        durations: dict[str, float] = {}
        for previous, current in zip(self.steps, self.steps[1:], strict=False):
            delta = current.clock_ms - previous.clock_ms
            if delta >= 0:
                durations[current.name] = round(delta, 1)
        return durations


def decode_console_output(raw: bytes) -> str:
    """Decode the bytes ``accoreconsole.exe`` wrote to a redirected stdout.

    Redirected Core Console output is UTF-16LE (often without a BOM); anything else is read as UTF-8
    and then as Windows-1252. NULs and backspaces (progress spinners) are dropped and line endings
    become ``\\n``.
    """
    if not raw:
        return ""
    if raw.startswith(b"\xff\xfe"):
        text = raw[2:].decode("utf-16-le", errors="replace")
    elif _looks_like_utf16le(raw):
        text = raw.decode("utf-16-le", errors="replace")
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
    text = text.replace("\x00", "").replace("\x08", "")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _looks_like_utf16le(raw: bytes) -> bool:
    sample = raw[:4096]
    high_bytes = sample[1::2]
    return len(high_bytes) >= 8 and high_bytes.count(0) >= 0.5 * len(high_bytes)


def _audit_counts(text: str, steps: Sequence[StepMark]) -> AuditCounts | None:
    """The AUDIT summary printed between the markers that frame the AUDIT command."""
    start = next((m.position for m in steps if m.name == "loaded"), None)
    end = next((m.position for m in steps if m.name == "audited"), None)
    if start is None or end is None or end <= start:
        return None
    region = text[start:end]
    matches = list(_AUDIT_TOTAL.finditer(region))
    if not matches:
        return None
    last = matches[-1]
    return AuditCounts(int(last.group(1)), int(last.group(2)), last.group(0).strip())


def _problems(text: str) -> tuple[str, ...]:
    found: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped or MARKER in stripped:
            continue
        if any(pattern.search(stripped) for pattern in _PROBLEM_PATTERNS) and stripped not in found:
            found.append(stripped)
            if len(found) == _MAX_PROBLEMS:
                break
    return tuple(found)


def parse_console_log(text: str) -> ConsoleLog:
    """Extract markers, checks, the AUDIT summary and problem lines from a decoded console log."""
    steps = tuple(
        StepMark(match.group(1), float(match.group(2)), match.start())
        for match in _STEP.finditer(text)
    )
    checks: dict[str, str] = {}
    for match in _CHECK.finditer(text):
        checks.setdefault(match.group(1), match.group(2).strip())
    return ConsoleLog(
        text=text,
        steps=steps,
        checks=checks,
        audit=_audit_counts(text, steps),
        problems=_problems(text),
    )
