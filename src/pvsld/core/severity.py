"""Severity levels shared by the rule pack and the design policy."""

from __future__ import annotations

from enum import StrEnum


class Severity(StrEnum):
    """``E`` blocks the drawing, ``W`` a warning a reviewer will likely raise, ``I`` info."""

    ERROR = "E"
    WARNING = "W"
    INFO = "I"
