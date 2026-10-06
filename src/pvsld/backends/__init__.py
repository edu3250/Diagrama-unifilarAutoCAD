"""Render backends (ADR-0001, layer L3) behind a single ``RenderBackend`` interface.

A backend only materializes the diagram model produced by :mod:`pvsld.core`; it decides no layout.

* B1, ezdxf: headless DXF R2018 plus a PNG/SVG preview. The default backend, built in Stage 2.1.
* B2, AutoCAD 2027: a .NET 10 plug-in reached over a current-user named pipe (native DWG, AutoCAD
  PDF plotting, live editing). Built after the S2 connectivity spike (Stage 2.2).
"""
