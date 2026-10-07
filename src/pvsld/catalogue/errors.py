"""Exceptions of the component catalogue.

Every problem found in a record is reported as one line that names the file and the field, so the
owner can fix a datasheet extraction without reading a Pydantic traceback::

    modules/x.yaml: variants.2: variant JINKO-X: vmp_v (50) must be lower than voc_v (49.3)
"""

from __future__ import annotations

from collections.abc import Sequence


class CatalogueError(Exception):
    """One or more records of the catalogue are invalid (or cannot be read).

    ``problems`` holds one human-readable line per problem; ``str(error)`` joins them.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        if not problems:
            raise ValueError("a CatalogueError needs at least one problem")
        self.problems: tuple[str, ...] = tuple(problems)
        super().__init__("\n".join(self.problems))


class UnknownComponentError(KeyError):
    """No component with the requested ``component_id`` is loaded in the registry."""

    def __init__(self, component_id: str, *, suggestions: Sequence[str] = ()) -> None:
        self.component_id = component_id
        self.suggestions: tuple[str, ...] = tuple(suggestions)
        super().__init__(component_id)

    def __str__(self) -> str:
        hint = f" (did you mean {', '.join(self.suggestions)}?)" if self.suggestions else ""
        return f"unknown component_id {self.component_id!r}{hint}"
