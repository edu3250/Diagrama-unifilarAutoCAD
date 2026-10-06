"""pvsld: generator of Mexican photovoltaic single-line diagrams for AutoCAD and DXF.

Layers, as decided in ADR-0001 (``docs/decisions/ADR-0001-claude-autocad-integration.md``):

* ``pvsld.core``: deterministic core (parameter model, calculations, rule-pack validation and a
  backend-neutral diagram model). Pure Python, no CAD dependency.
* ``pvsld.backends``: render backends that materialize the diagram model (ezdxf DXF first).
* ``pvsld.transports``: channels to out-of-process CAD hosts (AutoCAD COM spike, named pipe).
* ``pvsld.finishers``: optional post-processors (DXF to DWG 2018 and PDF).

The MCP server (L1) that exposes these layers to Claude arrives in Stage 2.3.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pvsld")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"

__all__ = ["__version__"]
