"""Deliverables beside the drawing (Stage 3.6.1, owner decisions 2026-10-09).

* :mod:`pvsld.report.bom`: the installation's bill of materials, as rows and as the plain-text
  summary shown to the user.
* :mod:`pvsld.report.memoria`: the calculation report (memoria de cálculo), as an Excel workbook
  with live formulas and as a PDF.
* :mod:`pvsld.report.project_sheet`: the professional-mode project sheet (hoja de proyecto), an
  Excel workbook with AUTO defaults and catalogue dropdowns, prefilled from a design.

All of them read a validated :class:`~pvsld.core.model.PvSystemSpec` and its
:class:`~pvsld.core.calc.Derived` values, so they work for any design, sized or hand-written.
"""

from pvsld.report.bom import BomLine, bill_of_materials, bom_text
from pvsld.report.memoria import Memoria, build_memoria, write_memoria_pdf, write_memoria_xlsx
from pvsld.report.project_sheet import write_project_sheet

__all__ = [
    "BomLine",
    "Memoria",
    "bill_of_materials",
    "bom_text",
    "build_memoria",
    "write_memoria_pdf",
    "write_memoria_xlsx",
    "write_project_sheet",
]
