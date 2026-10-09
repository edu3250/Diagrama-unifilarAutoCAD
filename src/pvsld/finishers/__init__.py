"""Optional finishers (ADR-0001): turn a B1 DXF into DWG 2018 and/or a plotted PDF.

* Core Console (``accoreconsole.exe``, :mod:`pvsld.finishers.core_console`), local and
  Windows-only, built in Stage 2.4 (spike S4). It needs the user's own licensed full AutoCAD and is
  never required: CI and users without AutoCAD keep the DXF. Because Core Console can fail silently
  without a licence, success is decided from the exit code, a timeout, progress markers in the
  console log and the output files themselves (:mod:`pvsld.finishers.console_log`,
  :mod:`pvsld.finishers.outputs`). :mod:`pvsld.finishers.fake` stands in for it in tests.

Planned: the APS Automation API (opt-in, the user's own credentials) and the ODA File Converter
(opt-in, installed and licensed by the user).
"""

from pvsld.finishers.core_console import (
    AutocadInfo,
    FinisherError,
    FinishOptions,
    FinishResult,
    detect_autocad,
    find_accoreconsole,
    finish,
)

__all__ = [
    "AutocadInfo",
    "FinishOptions",
    "FinishResult",
    "FinisherError",
    "detect_autocad",
    "find_accoreconsole",
    "finish",
]
