"""Transports to out-of-process CAD hosts (ADR-0001, spike S2).

Planned content (Stage 2.2):

* a throwaway pywin32 COM client for ``AutoCAD.Application.26``, kept only as the latency and
  reliability baseline for the plug-in;
* a newline-delimited JSON-RPC client for the B2 plug-in's current-user named pipe, protected by a
  secret generated at each start.

Both need the optional ``autocad`` extra (``pip install -e .[autocad]``) and a licensed local
AutoCAD, so they must stay out of the import path of :mod:`pvsld.core` and CI.
"""
