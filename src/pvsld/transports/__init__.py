"""Transports to out-of-process CAD hosts (ADR-0001, spike S2).

* :mod:`pvsld.transports.protocol`: the bridge wire protocol (newline-delimited JSON-RPC 2.0,
  error codes, exceptions).
* :mod:`pvsld.transports.pipe`: client for the B2 plug-in's current-user named pipe, with the
  per-start secret read from the discovery file.
* :mod:`pvsld.transports.streams`: byte streams with timeouts (Windows named pipe, TCP for tests).
* :mod:`pvsld.transports.fake`: an in-process fake of the plug-in for tests without AutoCAD.
* :mod:`pvsld.transports.com`: the throwaway pywin32 COM baseline for ``AutoCAD.Application.26``
  (measurement only).

Nothing here is imported by :mod:`pvsld.core`. The Windows-only parts import pywin32 lazily (it
ships with ``mcp`` on Windows and with the ``autocad`` extra), so the package imports on any OS
and the protocol tests run in CI without AutoCAD.
"""
