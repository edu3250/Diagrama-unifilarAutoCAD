"""The ``RenderBackend`` interface (ADR-0001, layer L3) shared by every renderer.

A backend only materializes a :class:`~pvsld.core.diagram.Diagram`; it never decides layout.
B1 (ezdxf, :mod:`pvsld.backends.dxf`) is the default. B2 (AutoCAD 2027 plug-in) arrives after the
S2 connectivity spike and must satisfy the same protocol, so tools and tests stay backend-agnostic.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from pvsld.core.diagram import Diagram


@dataclass(frozen=True)
class RenderResult:
    """What a backend produced: where, how big and a fingerprint of the bytes."""

    backend: str
    path: Path
    size_bytes: int
    sha256: str


def sha256_hex(data: bytes) -> str:
    """Lowercase hex SHA-256 of ``data`` (the fingerprint used by golden-file tests)."""
    return hashlib.sha256(data).hexdigest()


class RenderBackend(Protocol):
    """Materialize a diagram into a file."""

    name: str

    def render(self, diagram: Diagram, output: Path) -> RenderResult:
        """Write ``diagram`` to ``output`` and describe the result."""
        ...
