"""Decoding and parsing of the Core Console log (no AutoCAD needed)."""

from __future__ import annotations

from pathlib import Path

import pytest

from pvsld.finishers.console_log import decode_console_output, parse_console_log
from pvsld.finishers.core_console import FinishOptions, build_script, plan_paths


def _log(*lines: str) -> str:
    return "\n".join(lines) + "\n"


HEALTHY = _log(
    "Command: (progn ...)",
    "PVSLD:STEP:loaded:1000",
    "PVSLD:CHECK:entities:274",
    "PVSLD:CHECK:layouts:A3|",
    "PVSLD:CHECK:acadver:26.0s (LMS Tech)",
    "Command: _.AUDIT",
    "Fix any errors detected? [Yes/No] <N>: _N",
    "Auditing Header",
    "Total errors found 0 fixed 0",
    "PVSLD:STEP:audited:1100",
    "PVSLD:STEP:saved:1600",
    "PVSLD:STEP:plotted:3600",
    "PVSLD:STEP:end:3601",
)


# --- decoding ---------------------------------------------------------------------------------


def test_decodes_utf16le_without_bom() -> None:
    raw = "Comando: _.AUDIT\r\nTotal 0\r\n".encode("utf-16-le")
    assert decode_console_output(raw) == "Comando: _.AUDIT\nTotal 0\n"


def test_decodes_utf16le_with_bom_and_accents() -> None:
    raw = b"\xff\xfe" + "Auditoría completada\r\n".encode("utf-16-le")
    assert decode_console_output(raw) == "Auditoría completada\n"


def test_decodes_utf8_and_falls_back_to_cp1252() -> None:
    assert decode_console_output("línea\r\n".encode()) == "línea\n"
    assert decode_console_output("línea\r\n".encode("cp1252")) == "línea\n"


def test_drops_nuls_backspaces_and_bare_carriage_returns() -> None:
    assert decode_console_output(b"a\x08b\rc\x00") == "ab\nc"
    assert decode_console_output(b"") == ""


# --- markers ----------------------------------------------------------------------------------


def test_parses_steps_checks_and_audit() -> None:
    log = parse_console_log(HEALTHY)
    assert [mark.name for mark in log.steps] == ["loaded", "audited", "saved", "plotted", "end"]
    assert log.checks == {
        "entities": "274",
        "layouts": "A3|",
        "acadver": "26.0s (LMS Tech)",
    }
    assert log.audit is not None
    assert (log.audit.errors_found, log.audit.errors_fixed) == (0, 0)
    assert log.problems == ()
    assert log.step_durations_ms() == {"audited": 100, "saved": 500, "plotted": 2000, "end": 1}


def test_the_echo_of_the_script_never_counts_as_a_marker(tmp_path: Path) -> None:
    script = build_script(plan_paths(tmp_path / "sld.dxf"), FinishOptions())
    echoed = "\n".join(f"Command: {line}" for line in script.split("\r\n"))
    log = parse_console_log(echoed)
    assert log.steps == ()
    assert log.checks == {}


def test_a_negative_step_duration_after_midnight_is_dropped() -> None:
    log = parse_console_log(_log("PVSLD:STEP:loaded:86399900", "PVSLD:STEP:audited:50"))
    assert log.step_durations_ms() == {}


def test_step_lookup_returns_none_for_a_missing_step() -> None:
    log = parse_console_log(_log("PVSLD:STEP:loaded:5"))
    assert log.step("loaded") is not None
    assert log.step("plotted") is None


# --- AUDIT ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("Total errors found 3 fixed 2", (3, 2)),
        ("Total de errores encontrados 0 corregidos 0", (0, 0)),
        ("Total de errores encontrados 2, corregidos 0", (2, 0)),  # AutoCAD 2027 Spanish (S4)
        ("Total de errores encontrados: 7, reparados: 0.", (7, 0)),
    ],
)
def test_audit_summary_in_english_and_spanish(line: str, expected: tuple[int, int]) -> None:
    log = parse_console_log(_log("PVSLD:STEP:loaded:1", line, "PVSLD:STEP:audited:2"))
    assert log.audit is not None
    assert (log.audit.errors_found, log.audit.errors_fixed) == expected


def test_audit_summary_outside_the_audit_region_is_ignored() -> None:
    text = _log(
        "Total errors found 9 fixed 9",
        "PVSLD:STEP:loaded:1",
        "PVSLD:STEP:audited:2",
        "Total errors found 5 fixed 0",
    )
    assert parse_console_log(text).audit is None


def test_audit_is_none_when_the_markers_are_missing() -> None:
    assert parse_console_log("Total errors found 0 fixed 0\n").audit is None


# --- problems ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        'Unknown command "FOO".  Press F1 for help.',
        'Comando desconocido "FOO". Pulse F1 para obtener ayuda.',
        "Invalid or incomplete DXF input -- drawing discarded.",
        "Entrada DXF no válida o incompleta; dibujo descartado.",
        "; error: bad argument type: stringp nil",
        "; error: tipo de argumento erróneo: stringp nil",
        "*Invalid*",
        "Unable to open file.",
        "No se ha podido abrir el archivo.",
        "Plot cancelled.",
        "This drawing may have been saved by an application not developed or licensed by Autodesk.",
        "License not found.",
        "No valid license available.",
        "Licencia no válida.",
        "No se pudo obtener una licencia.",
        "Unhandled Exception: System.AccessViolationException",
    ],
)
def test_problem_phrases_are_reported(line: str) -> None:
    assert parse_console_log(_log("ok", line)).problems == (line,)


@pytest.mark.parametrize(
    "line",
    [
        "Total errors found 0 fixed 0",
        "Total de errores encontrados 0 corregidos 0",
        "AutoCAD 2027 - EDUCACIÓN (NO COMERCIAL)",
        "Licencia: Educación",
        "Regenerating model.",
        "PVSLD:STEP:loaded:1",
        "Effective plotting area:  287.00 wide by 410.00 high",
    ],
)
def test_benign_lines_are_not_problems(line: str) -> None:
    assert parse_console_log(_log(line)).problems == ()


# --- excerpts of real AutoCAD 2027 (Spanish) Core Console logs, recorded in spike S4 ---------


def _echo(step: str) -> str:
    """How Core Console echoes the script line of a step marker."""
    marker = f'(strcat "\\nPVSLD" ":STEP:{step}:" (itoa (getvar "MILLISECS")) "\\n")'
    return f"Comando: (progn (princ {marker}) (princ))"


REAL_AUDIT = (
    _echo("loaded")
    + """

PVSLD:STEP:loaded:2304828

Comando: _.AUDIT

¿Corregir errores detectados? [Sí/No] <N>: _N

Encabezamiento de auditoría

Tablas de auditoría

Paso 1 de entidades de auditoría

Fase 1 200     objetos revisadosAcDbViewport(123)
           Paperspace vport layer Not "0"               "0"
AcDbViewport(123)                 no se ha reparado.
Fase 1 800     objetos revisados
Paso 2 de entidades de auditoría

Fase 2 200     objetos revisadosAcDbViewport(123)
           Paperspace vport layer Not "0"               "0"
AcDbViewport(123)                 no se ha reparado.
Fase 2 800     objetos revisados
Bloques de auditoría

 9             Bloques revisados

Revisando AcDsRecords

Total de errores encontrados 2, corregidos 0

0 objetos borrados

"""
    + _echo("audited")
    + """

PVSLD:STEP:audited:2304859
"""
)


def test_real_spanish_audit_with_the_s1_viewport_error() -> None:
    log = parse_console_log(REAL_AUDIT)
    assert log.audit is not None
    assert (log.audit.errors_found, log.audit.errors_fixed) == (2, 0)
    assert log.step_durations_ms() == {"audited": 31}
    assert log.problems == ()  # the AUDIT summary, not the detail lines, decides


def test_real_invalid_dxf_lines_are_problems() -> None:
    text = _log(
        "Error en el encabezamiento del dibujo en línea 5.",
        "D:\\work\\broken.dxf no es un archivo DXF válido",
        "Entrada DXF no válida o incompleta -- dibujo descartado.",
        "ERROR: Something went wrong. ErrorStatus=53 (AcCoreConsole.cpp:1792).",
    )
    assert len(parse_console_log(text).problems) == 4


def test_real_rejected_plotter_answer_is_a_problem() -> None:
    text = _log(
        "Introduzca un nombre de dispositivo de salida o [?] <DWG to PDF.pc3>: NoSuch.pc3",
        "<NoSuch.pc3> no encontrado.",
    )
    assert parse_console_log(text).problems == ("<NoSuch.pc3> no encontrado.",)


def test_real_banner_and_plot_lines_are_not_problems() -> None:
    text = _log(
        "AutoCAD Core Engine Console - Copyright 2026 Autodesk, Inc.  All rights reserved.",
        "Isolating to regkey=pvsld, userDataFolder=D:\\out\\.accoreconsole-user.",
        "INFO: Isolation create time: 193 ms.",
        "**** Variable de sistema modificada ****",
        "2 de las variables de sistema supervisadas se han cambiado desde el valor deseado.",
        "Utilidades de menú de AutoCAD cargadas.",
        "Área efectiva de trazado:  420.00 de anchura por 297.00 de altura",
        "Trazando ventana gráfica 2.",
        "¿Desea realmente desechar todos los cambios realizados al dibujo? <N> _Y",
    )
    assert parse_console_log(text).problems == ()


def test_problems_are_deduplicated_and_capped() -> None:
    text = _log(*(["Unknown command"] * 3), *(f"Unable to do {n}" for n in range(30)))
    problems = parse_console_log(text).problems
    assert problems[0] == "Unknown command"
    assert problems.count("Unknown command") == 1
    assert len(problems) == 20
