"""Deterministic core (ADR-0001, layer L2). Pure Python with no CAD dependency.

Planned content, built from Stage 2.1 (S1) onwards:

1. the parameter model (Pydantic, published as JSON Schema 2020-12, with ``schema_version``);
2. calculations (temperature-corrected Voc, string limits, ampacity, OCPD, voltage drop);
3. validation against the versioned Mexican rule pack ``mx-gd-2026.10``;
4. the backend-neutral diagram model, which carries the whole layout in sheet millimetres.

Claude never draws geometry: everything on the sheet is computed here, so every render backend
is a thin materializer and the backends stay in parity.
"""
