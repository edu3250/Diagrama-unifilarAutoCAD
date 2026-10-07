"""Deterministic core (ADR-0001, layer L2). Pure Python with no CAD dependency.

Pipeline, in the order the data flows:

1. ``model``: the parameter model (Pydantic v2, JSON Schema 2020-12, ``schema_version``).
2. ``tables`` and ``calc``: NOM tables as data keyed by edition, and the calculations
   (temperature-corrected Voc, string limits, design currents, OCPD, ampacity, voltage drop).
3. ``rules`` and ``validation``: the versioned rule pack ``mx-gd-2026.10`` and the entry point
   ``validate_pv_design``.
4. ``layers``, ``diagram`` and ``layout``: the house layer standard, the backend-neutral diagram
   model and the layout template that fills it, in sheet millimetres.

Claude never draws geometry: everything on the sheet is computed here, so every render backend
is a thin materializer and the backends stay in parity.
"""
