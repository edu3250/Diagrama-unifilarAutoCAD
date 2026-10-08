"""Symbol library (ADR-0005): the CFE block library the generator draws with.

The blocks are defined in :mod:`pvsld.symbols.cfe.definitions` and kept in
``symbols/pvsld-symbols-cfe.dxf``; the DXF backend imports them from that file
(:func:`pvsld.symbols.cfe.loader.library_document`). This module is the interface the layout,
the diagram model and the MCP server use.
"""

from pvsld.symbols.cfe.definitions import LIBRARY, SYMBOLS, combiner_name, get_symbol
from pvsld.symbols.cfe.model import (
    APP_ID,
    BLOCK_PREFIX,
    LIBRARY_VERSION,
    AttDef,
    Port,
    SymbolSpec,
)


def symbol_catalogue() -> list[dict[str, object]]:
    """The whole library as plain data (``pvsld://symbols`` resource, documentation)."""
    return [spec.to_dict() for spec in LIBRARY]


__all__ = [
    "APP_ID",
    "BLOCK_PREFIX",
    "LIBRARY",
    "LIBRARY_VERSION",
    "SYMBOLS",
    "AttDef",
    "Port",
    "SymbolSpec",
    "combiner_name",
    "get_symbol",
    "symbol_catalogue",
]
