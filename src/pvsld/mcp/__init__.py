"""MCP server of the project (layer L1 of ADR-0001): validate and generate over stdio.

Start it with the ``pvsld-mcp`` console script or ``python -m pvsld.mcp``. The tools are thin
wrappers over :mod:`pvsld.service`; the sandbox that confines every file write is in
:mod:`pvsld.mcp.sandbox`.

Importing this package does not import the MCP SDK or matplotlib, so ``import pvsld`` stays cheap.
"""

__all__ = ["create_server", "main"]


def __getattr__(name: str) -> object:
    if name in __all__:
        from pvsld.mcp import server

        return getattr(server, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
