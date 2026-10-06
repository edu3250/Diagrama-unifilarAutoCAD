"""Core Console finisher (ADR-0001, spike S4): DXF to DWG 2018 and PDF with ``accoreconsole.exe``.

One call of :func:`finish` handles one drawing:

1. it writes a script (``.scr``) next to the outputs: progress markers, ``AUDIT`` (report only by
   default), ``SAVEAS`` 2018, ``-PLOT`` of the paper-space layout with a PC3 (``DWG To PDF.pc3``),
   ``QUIT``;
2. it runs ``accoreconsole.exe /i <drawing> /s <script>`` with stdout redirected to a file and a
   timeout (on expiry only the process it started is stopped);
3. it decodes and parses the console log and inspects the files it asked for.

The result is never a silent success. Core Console run without a usable licence (for example
outside the Windows session that holds a named-user licence) has been reported to exit silently or
hang. :class:`FinishResult` is therefore ``ok`` only when the process exited with code 0 inside the
timeout, every script marker was printed, AUDIT reported 0 errors, no problem phrase was logged,
and each requested file was produced by this run with the expected format (DWG ``AC1032``, a PDF
with at least one page).

Commands use the ``_.`` prefix and keywords the ``_`` prefix, so the script also works in localized
builds (the reference workstation runs the Spanish AutoCAD 2027). Windows only; CI covers it with a
fake runner (``tests/test_finisher_*.py``).
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import time
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pvsld.finishers.console_log import (
    AuditCounts,
    ConsoleLog,
    decode_console_output,
    parse_console_log,
)
from pvsld.finishers.outputs import DwgInfo, PdfInfo, inspect_dwg, inspect_pdf

__all__ = [
    "DEFAULT_PLOTTER",
    "ENV_ACCORECONSOLE",
    "EXPECTED_DWG_VERSION",
    "FinishOptions",
    "FinishPaths",
    "FinishResult",
    "FinisherError",
    "ProcessOutcome",
    "Runner",
    "build_command",
    "build_script",
    "find_accoreconsole",
    "finish",
    "plan_paths",
    "run_process",
]

ENV_ACCORECONSOLE = "PVSLD_ACCORECONSOLE"
DEFAULT_PLOTTER = "DWG To PDF.pc3"
DEFAULT_LAYOUT = "A3"
DEFAULT_PLOT_STYLE = "monochrome.ctb"
# A sheet takes about 4.5 s (S4). A script out of step leaves Core Console waiting for input for
# ever, so the timeout is the only way such a run ends.
DEFAULT_TIMEOUT_S = 60.0
EXPECTED_DWG_VERSION = "AC1032"
ISOLATE_USER = "pvsld"
EXECUTABLE = "accoreconsole.exe"
# Markers the script prints, in order; each closes the step named in STEP_LABELS.
STEP_ORDER = ("loaded", "audited", "saved", "plotted", "end")
STEP_LABELS = {"audited": "audit", "saved": "saveas", "plotted": "plot", "end": "script_end"}
_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class FinisherError(RuntimeError):
    """The finisher cannot start (no Core Console, unusable path, existing output); the message is
    safe to show the user."""


@dataclass(frozen=True)
class FinishOptions:
    """What to produce and how.

    Attributes:
        dwg: save a DWG 2018 (``AC1032``) next to the source.
        pdf: plot the layout to a PDF.
        layout: paper-space layout to plot.
        plotter: PC3 used for the PDF; it must exist in the AutoCAD plotter search path.
        paper: media name for a detailed plot configuration; ``None`` keeps the layout's page setup.
        plot_style: plot style table used with ``paper`` (``"."`` for none).
        audit_fix: let AUDIT fix what it finds (it always reports the counts).
        open_mode: ``"argument"`` passes the drawing with ``/i``; ``"dxfin"`` starts on the default
            drawing and imports the DXF with ``DXFIN``.
        isolate: run with ``/isolate`` so Core Console keeps its user data in the output folder
            instead of the owner's AutoCAD profile.
        timeout_s: wall-clock limit for the process.
        overwrite: delete outputs of an earlier run first; otherwise existing outputs are an error.
    """

    dwg: bool = True
    pdf: bool = True
    layout: str = DEFAULT_LAYOUT
    plotter: str = DEFAULT_PLOTTER
    paper: str | None = None
    plot_style: str = DEFAULT_PLOT_STYLE
    audit_fix: bool = False
    open_mode: Literal["argument", "dxfin"] = "argument"
    isolate: bool = True
    timeout_s: float = DEFAULT_TIMEOUT_S
    overwrite: bool = False


@dataclass(frozen=True)
class FinishPaths:
    """Files of one finisher run, all inside ``out_dir``."""

    source: Path
    out_dir: Path
    dwg: Path
    pdf: Path
    script: Path
    log: Path
    raw_output: Path
    isolate_dir: Path

    def outputs(self, options: FinishOptions) -> list[Path]:
        """Files this run writes and must find afterwards (DWG and/or PDF)."""
        return [
            path for path, wanted in ((self.dwg, options.dwg), (self.pdf, options.pdf)) if wanted
        ]


@dataclass(frozen=True)
class ProcessOutcome:
    """How the Core Console process ended."""

    exit_code: int | None
    output: bytes
    timed_out: bool
    duration_s: float
    pid: int | None = None


Runner = Callable[[Sequence[str], Path, float, Path], ProcessOutcome]
"""``runner(command, cwd, timeout_s, raw_output_path)``; :func:`run_process` is the real one."""


@dataclass(frozen=True)
class FinishResult:
    """Outcome of :func:`finish`; ``ok`` is ``True`` only when ``problems`` is empty."""

    ok: bool
    source: Path
    paths: FinishPaths
    options: FinishOptions
    command: tuple[str, ...]
    process: ProcessOutcome | None
    log: ConsoleLog
    dwg: DwgInfo | None = None
    pdf: PdfInfo | None = None
    step_ms: dict[str, float] = field(default_factory=dict)
    problems: tuple[str, ...] = ()

    @property
    def audit(self) -> AuditCounts | None:
        return self.log.audit

    @property
    def duration_s(self) -> float | None:
        return None if self.process is None else round(self.process.duration_s, 3)

    def to_dict(self) -> dict[str, Any]:
        """Plain JSON types (for the CLI ``--json`` and a later MCP tool)."""
        audit = self.log.audit
        return {
            "ok": self.ok,
            "source": str(self.source),
            "dwg_path": str(self.paths.dwg) if self.options.dwg else None,
            "pdf_path": str(self.paths.pdf) if self.options.pdf else None,
            "log_path": str(self.paths.log),
            "script_path": str(self.paths.script),
            "command": list(self.command),
            "pid": None if self.process is None else self.process.pid,
            "exit_code": None if self.process is None else self.process.exit_code,
            "timed_out": False if self.process is None else self.process.timed_out,
            "duration_s": self.duration_s,
            "step_ms": self.step_ms,
            "audit": None
            if audit is None
            else {"errors_found": audit.errors_found, "errors_fixed": audit.errors_fixed},
            "checks": self.log.checks,
            "dwg": None
            if self.dwg is None
            else {
                "version": self.dwg.version,
                "release": self.dwg.release,
                "size_bytes": self.dwg.size_bytes,
                "trusted_dwg": self.dwg.trusted,
                "trusted_dwg_text": self.dwg.trusted_dwg_text,
                "product_information": list(self.dwg.product_information),
                "summary_properties": list(self.dwg.summary_properties),
                "markings": [m.context for m in self.dwg.markings],
            },
            "pdf": None
            if self.pdf is None
            else {
                "version": self.pdf.version,
                "pages": self.pdf.pages,
                "page_sizes_mm": [list(size) for size in self.pdf.page_sizes_mm],
                "size_bytes": self.pdf.size_bytes,
                "producer": self.pdf.producer,
                "creator": self.pdf.creator,
                "markings": [m.context for m in self.pdf.markings],
            },
            "problems": list(self.problems),
        }


# --- locating the Core Console --------------------------------------------------------------


def _default_program_dirs(environ: Mapping[str, str]) -> list[Path]:
    autodesk = Path(
        environ.get("ProgramW6432") or environ.get("ProgramFiles") or r"C:\Program Files"
    )
    autodesk /= "Autodesk"
    if not autodesk.is_dir():
        return []
    # Newest release first: "AutoCAD 2027" sorts after "AutoCAD 2026".
    return sorted(autodesk.glob("AutoCAD 20[0-9][0-9]"), reverse=True)


def find_accoreconsole(
    explicit: Path | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    program_dirs: Iterable[Path] | None = None,
) -> Path | None:
    """Locate ``accoreconsole.exe``: an explicit path, ``$PVSLD_ACCORECONSOLE``, then the newest
    ``%ProgramFiles%\\Autodesk\\AutoCAD 20xx``. Returns ``None`` when none exists."""
    environ = os.environ if environ is None else environ
    if explicit is not None:
        return explicit if explicit.is_file() else None
    configured = environ.get(ENV_ACCORECONSOLE)
    if configured:
        path = Path(configured)
        return path if path.is_file() else None
    dirs = _default_program_dirs(environ) if program_dirs is None else program_dirs
    for directory in dirs:
        candidate = directory / EXECUTABLE
        if candidate.is_file():
            return candidate
    return None


# --- script and command line ----------------------------------------------------------------


def plan_paths(source: Path, out_dir: Path | None = None) -> FinishPaths:
    """Output paths for ``source``: ``<out_dir>/<stem>.dwg``, ``.pdf``, ``.scr`` and logs."""
    source = source.resolve()
    out_dir = (out_dir or source.parent).resolve()
    stem = source.stem
    return FinishPaths(
        source=source,
        out_dir=out_dir,
        dwg=out_dir / f"{stem}.dwg",
        pdf=out_dir / f"{stem}.pdf",
        script=out_dir / f"{stem}.finish.scr",
        log=out_dir / f"{stem}.accoreconsole.log",
        raw_output=out_dir / f"{stem}.accoreconsole.raw",
        isolate_dir=out_dir / ".accoreconsole-user",
    )


def _script_value(value: str, what: str) -> str:
    """A value that can sit on one script line: printable ASCII, no quote."""
    if not value or not value.isascii() or not value.isprintable() or '"' in value:
        raise FinisherError(
            f"{what} {value!r} cannot be written to a Core Console script: use printable ASCII "
            "without double quotes (non-ASCII paths are not supported yet)"
        )
    return value


def _script_path(path: Path) -> str:
    """An absolute path for a file prompt; quoted when it contains a space (a space is Enter)."""
    text = _script_value(str(path), "path")
    return f'"{text}"' if " " in text else text


def _marker(kind: str, name: str, expression: str) -> str:
    # The marker text is split ("PVSLD" ":STEP:...") so the echo of this line never matches; (princ)
    # at the end keeps AutoLISP from echoing the return value.
    return f'(progn (princ (strcat "\\nPVSLD" ":{kind}:{name}:" {expression} "\\n")) (princ))'


# MILLISECS has millisecond resolution; DATE only advances in whole seconds in Core Console (S4).
_CLOCK_MS = '(itoa (getvar "MILLISECS"))'
# (layoutlist) is not defined in Core Console; the layout dictionary is (3 . name) pairs.
_LAYOUT_NAMES = (
    '(apply \'strcat (mapcar \'(lambda (p) (if (= (car p) 3) (strcat (cdr p) "|") "")) '
    '(dictsearch (namedobjdict) "ACAD_LAYOUT")))'
)


def _step(name: str) -> str:
    return _marker("STEP", name, _CLOCK_MS)


_CHECKS = (
    _marker("CHECK", "acadver", '(getvar "ACADVER")'),
    _marker("CHECK", "locale", '(getvar "LOCALE")'),
    _marker("CHECK", "dwgname", '(getvar "DWGNAME")'),
    _marker(
        "CHECK",
        "entities",
        '(itoa (if (setq pvsld_ss (ssget "_X")) (sslength pvsld_ss) 0))',
    ),
    _marker("CHECK", "layouts", _LAYOUT_NAMES),
)


def _plot_lines(paths: FinishPaths, options: FinishOptions) -> list[str]:
    layout = _script_value(options.layout, "layout")
    plotter = _script_value(options.plotter, "plotter")
    pdf = _script_path(paths.pdf)
    if options.paper is None:
        # The layout's own page setup (paper, area, scale) with the given device.
        return ["_.-PLOT", "_N", layout, "", plotter, pdf, "_N", "_Y"]
    paper = _script_value(options.paper, "paper")
    style = _script_value(options.plot_style, "plot style")
    return [
        "_.-PLOT",
        "_Y",  # detailed plot configuration
        layout,
        plotter,
        paper,
        "_M",  # millimetres
        "_L",  # landscape
        "_N",  # upside down
        "_L",  # plot area: layout
        "1:1",
        "0,0",
        "_Y",  # plot with plot styles
        style,
        "_Y",  # plot with lineweights
        "_N",  # scale lineweights
        "_N",  # paper space first
        "_N",  # hide paper-space objects
        pdf,
        "_N",  # save changes to the page setup
        "_Y",  # proceed
    ]


def build_script(paths: FinishPaths, options: FinishOptions) -> str:
    """The ``.scr`` text (CRLF line endings, final Enter) for one finisher run."""
    lines: list[str] = []
    if options.open_mode == "dxfin":
        lines += ["_.DXFIN", _script_path(paths.source)]
    lines += [_step("loaded"), *_CHECKS]
    lines += ["_.AUDIT", "_Y" if options.audit_fix else "_N", _step("audited")]
    if options.dwg:
        lines += ["_.SAVEAS", "_2018", _script_path(paths.dwg)]
    lines.append(_step("saved"))
    if options.pdf:
        lines += _plot_lines(paths, options)
    lines += [_step("plotted"), _step("end"), "_.QUIT", "_Y"]
    return "\r\n".join(lines) + "\r\n"


def build_command(executable: Path, paths: FinishPaths, options: FinishOptions) -> list[str]:
    """``accoreconsole.exe [/i drawing] /s script [/isolate user folder]``."""
    command = [str(executable)]
    if options.open_mode == "argument":
        command += ["/i", str(paths.source)]
    command += ["/s", str(paths.script)]
    if options.isolate:
        command += ["/isolate", ISOLATE_USER, str(paths.isolate_dir)]
    return command


# --- running ----------------------------------------------------------------------------------


def run_process(
    command: Sequence[str], cwd: Path, timeout_s: float, raw_output: Path
) -> ProcessOutcome:
    """Run ``command`` with stdout and stderr in ``raw_output`` and stdin closed.

    Output goes to a file rather than a pipe, so a helper process that inherits the handle cannot
    keep the run open. On timeout only the process started here is stopped (``Popen.kill``).
    """
    started = time.perf_counter()
    with raw_output.open("wb") as sink:
        process = subprocess.Popen(
            list(command),
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=sink,
            stderr=subprocess.STDOUT,
            creationflags=_CREATE_NO_WINDOW,
        )
        timed_out = False
        try:
            process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            with contextlib.suppress(subprocess.TimeoutExpired):
                # The kill is already issued and the run is reported as timed out; a slow reap
                # must not turn that report into an unhandled exception (exit_code stays None).
                process.wait(timeout=30)
    duration = time.perf_counter() - started
    return ProcessOutcome(
        exit_code=process.returncode,
        output=raw_output.read_bytes(),
        timed_out=timed_out,
        duration_s=duration,
        pid=process.pid,
    )


def _prepare(paths: FinishPaths, options: FinishOptions) -> None:
    if not paths.source.is_file():
        raise FinisherError(f"drawing not found: {paths.source}")
    if paths.source.suffix.lower() not in {".dxf", ".dwg"}:
        raise FinisherError(f"expected a .dxf or .dwg drawing, got {paths.source.name}")
    if options.open_mode == "dxfin" and paths.source.suffix.lower() != ".dxf":
        raise FinisherError("open_mode 'dxfin' only imports .dxf drawings")
    targets = paths.outputs(options)
    if paths.source in targets:
        raise FinisherError(f"the source {paths.source.name} would be overwritten by an output")
    existing = [path for path in targets if path.exists()]
    if existing and not options.overwrite:
        names = ", ".join(path.name for path in existing)
        raise FinisherError(f"output exists: {names}; pass overwrite to replace it")
    paths.out_dir.mkdir(parents=True, exist_ok=True)
    for path in (*existing, paths.log, paths.raw_output):
        path.unlink(missing_ok=True)
    if options.isolate:
        paths.isolate_dir.mkdir(exist_ok=True)


def _step_ms(log: ConsoleLog, process: ProcessOutcome) -> dict[str, float]:
    """Durations of the scripted steps (AutoCAD's ``MILLISECS``) and of everything around them.

    ``outside_script`` is the process wall time minus the scripted part: process start, licence
    check, loading the drawing given with ``/i``, and exit.
    """
    durations = {
        STEP_LABELS.get(name, name): value for name, value in log.step_durations_ms().items()
    }
    loaded, end = log.step("loaded"), log.step("end")
    if loaded is not None and end is not None and end.clock_ms >= loaded.clock_ms:
        scripted = end.clock_ms - loaded.clock_ms
        durations["outside_script"] = round(process.duration_s * 1000 - scripted, 1)
    return durations


def _assess(
    paths: FinishPaths,
    options: FinishOptions,
    process: ProcessOutcome,
    log: ConsoleLog,
    started_wall: float,
) -> tuple[list[str], DwgInfo | None, PdfInfo | None]:
    problems: list[str] = []
    if process.timed_out:
        problems.append(
            f"accoreconsole did not finish within {options.timeout_s:g} s; the process this "
            f"finisher started (pid {process.pid}) was stopped"
        )
    elif process.exit_code != 0:
        problems.append(f"accoreconsole exited with code {process.exit_code}")
    if not log.text.strip():
        problems.append(
            "accoreconsole printed nothing; it does this when no AutoCAD licence is usable in "
            "this Windows session"
        )
    missing = [name for name in STEP_ORDER if log.step(name) is None]
    if missing:
        problems.append(
            "the script stopped before step(s) "
            + ", ".join(missing)
            + " (drawing not loaded, licence refused or a prompt out of step)"
        )
    if log.step("loaded") is not None:
        entities = log.checks.get("entities", "")
        if not entities.isdigit() or int(entities) == 0:
            problems.append(f"the drawing loaded without entities (count {entities or 'missing'})")
        if options.pdf and options.layout not in log.checks.get("layouts", "").split("|"):
            problems.append(f"layout {options.layout!r} is not in the drawing")
    if log.step("audited") is not None:
        if log.audit is None:
            problems.append("the AUDIT summary was not found in the console log")
        elif log.audit.errors_found:
            problems.append(
                f"AUDIT found {log.audit.errors_found} errors "
                f"(fixed {log.audit.errors_fixed}): {log.audit.line}"
            )
    problems += [f"console: {line}" for line in log.problems]

    dwg_info: DwgInfo | None = None
    pdf_info: PdfInfo | None = None
    for path in paths.outputs(options):
        if not path.is_file():
            problems.append(f"not produced: {path}")
        elif path.stat().st_mtime < started_wall - 2:
            problems.append(f"stale output (older than this run): {path}")
    if options.dwg and paths.dwg.is_file():
        dwg_info = inspect_dwg(paths.dwg)
        if dwg_info.version != EXPECTED_DWG_VERSION:
            problems.append(
                f"DWG version is {dwg_info.version or 'unreadable'}, "
                f"expected {EXPECTED_DWG_VERSION} (DWG 2018)"
            )
    if options.pdf and paths.pdf.is_file():
        pdf_info = inspect_pdf(paths.pdf)
        if not pdf_info.header_ok or pdf_info.pages < 1:
            problems.append(f"PDF is not a valid document with pages: {paths.pdf}")
    return problems, dwg_info, pdf_info


def finish(
    source: Path,
    out_dir: Path | None = None,
    *,
    options: FinishOptions | None = None,
    accoreconsole: Path | None = None,
    runner: Runner = run_process,
) -> FinishResult:
    """Turn ``source`` (DXF or DWG) into the requested DWG 2018 and/or PDF with Core Console.

    With ``dwg`` and ``pdf`` both off, the run only opens the drawing and audits it (a check that a
    file opens cleanly in AutoCAD).

    Raises:
        FinisherError: Core Console is not found, a path cannot be scripted, the source is missing
            or an output exists without ``overwrite``. Everything that happens once the process
            has started is reported in the result instead.
    """
    options = options or FinishOptions()
    executable = find_accoreconsole(accoreconsole)
    if executable is None:
        where = accoreconsole or f"${ENV_ACCORECONSOLE} or %ProgramFiles%\\Autodesk\\AutoCAD 20xx"
        raise FinisherError(f"{EXECUTABLE} not found ({where}); a full AutoCAD is required")
    paths = plan_paths(source, out_dir)
    script = build_script(paths, options)  # validates every scripted value before touching files
    command = build_command(executable, paths, options)
    _prepare(paths, options)
    paths.script.write_bytes(script.encode("ascii"))

    started_wall = time.time()
    process = runner(command, paths.out_dir, options.timeout_s, paths.raw_output)
    text = decode_console_output(process.output)
    paths.log.write_text(text, encoding="utf-8")
    log = parse_console_log(text)
    problems, dwg_info, pdf_info = _assess(paths, options, process, log, started_wall)
    return FinishResult(
        ok=not problems,
        source=paths.source,
        paths=paths,
        options=options,
        command=tuple(command),
        process=process,
        log=log,
        dwg=dwg_info,
        pdf=pdf_info,
        step_ms=_step_ms(log, process),
        problems=tuple(problems),
    )
