"""Where the bundled data lives: inside the installed package, or in this repository.

The plugin (Stage 3.6.4) runs the server from a wheel that ``uvx`` builds from a git tag, with no
repository around it. The wheel therefore carries the data the code reads at run time under
``pvsld/_data`` (``force-include`` in ``pyproject.toml``), with the same relative paths as in the
repository:

* ``datasheets/records``: the component catalogue;
* ``symbols/pvsld-symbols.dxf``: the symbol library;
* ``sheet_templates/a3_plantilla_v1.dxf``: the owner's neutral A3 sheet;
* ``examples/residential_7p7kwp.yaml``: the sample the sizing-template resource is cut from.

:func:`data_path` prefers the packaged copy and falls back to the repository checkout, so a
development install (editable, where nothing is copied) keeps reading the files it edits.
"""

from __future__ import annotations

from pathlib import Path

__all__ = ["PACKAGE_DATA", "REPOSITORY", "data_path"]

PACKAGE_DATA = Path(__file__).resolve().parent / "_data"
REPOSITORY = Path(__file__).resolve().parents[2]


def data_path(relative: str) -> Path:
    """The packaged copy of ``relative`` (a repository-relative path), else the repository's.

    The repository path is returned even when it does not exist, so a caller's own "not found"
    message names a place a developer recognises.
    """
    packaged = PACKAGE_DATA / relative
    return packaged if packaged.exists() else REPOSITORY / relative
