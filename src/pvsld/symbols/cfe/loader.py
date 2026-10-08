"""Import blocks of the symbol library DXF into another drawing (what Stage 4.3 needs).

ezdxf's :class:`~ezdxf.addons.Importer` copies a block with its entities, layers, linetypes and
text styles, but not the XDATA of the block record, which is where ADR-0003 keeps the ports. The
generator would then place symbols whose ports a reader cannot find. :func:`import_blocks` copies
the block XDATA as well, so an imported block is indistinguishable from the library's.
"""

from __future__ import annotations

import functools
import os
from collections.abc import Iterable
from pathlib import Path

import ezdxf
from ezdxf.addons import Importer
from ezdxf.document import Drawing
from ezdxf.lldxf.const import DXFValueError

from pvsld.symbols.cfe.build import LIBRARY_FILE, build_document
from pvsld.symbols.cfe.definitions import combiner_name, get_symbol
from pvsld.symbols.cfe.model import APP_ID, BLOCK_PREFIX, LIBRARY_VERSION

LIBRARY_ENV = "PVSLD_SYMBOL_LIBRARY"
"""Environment variable naming another library DXF (for example a copy next to an installed
plug-in); it must carry the library version of this package."""
_REPO_LIBRARY = Path(__file__).resolve().parents[4] / LIBRARY_FILE


def load_library(path: Path) -> Drawing:
    """Read the library DXF at ``path``."""
    return ezdxf.readfile(path)


def library_path() -> Path | None:
    """The library DXF the generator reads: ``$PVSLD_SYMBOL_LIBRARY``, else the repository file.

    ``None`` when neither exists (an installed package without the repository); the generator
    then renders the same blocks from the definitions in memory.
    """
    configured = os.environ.get(LIBRARY_ENV)
    if configured:
        return Path(configured)
    return _REPO_LIBRARY if _REPO_LIBRARY.is_file() else None


@functools.cache
def _library_document(path: Path | None) -> Drawing:
    if path is None:
        return build_document()
    doc = load_library(path)
    version = doc.ezdxf_metadata().get("PVSLD_LIBRARY_VERSION")
    if version != LIBRARY_VERSION:
        raise ValueError(
            f"{path} is symbol library {version}, this package draws with {LIBRARY_VERSION}; "
            "run 'pvsld symbols build'"
        )
    return doc


def library_document() -> Drawing:
    """The symbol library the generator imports blocks from (read once per process and path).

    Raises:
        ValueError: the file is a different library version than the definitions.
        OSError: the configured file cannot be read.
    """
    return _library_document(library_path())


def import_blocks(
    source: Drawing, target: Drawing, names: Iterable[str] | None = None
) -> list[str]:
    """Copy ``names`` (default: every ``PVSLD_`` block) from ``source`` into ``target``.

    Existing blocks of the same name in ``target`` are left alone. Returns the imported names.

    Raises:
        KeyError: a requested block is not in ``source``.
    """
    wanted = (
        [b.name for b in source.blocks if b.name.startswith(BLOCK_PREFIX)]
        if names is None
        else list(names)
    )
    missing = [name for name in wanted if name not in source.blocks]
    if missing:
        raise KeyError(f"blocks not in the library: {', '.join(missing)}")
    todo = [name for name in wanted if name not in target.blocks]
    if APP_ID not in target.appids:
        target.appids.add(APP_ID)
    importer = Importer(source, target)
    importer.import_blocks(todo)
    importer.finalize()
    for name in todo:
        try:
            xdata = source.blocks.get(name).block_record.get_xdata(APP_ID)
        except DXFValueError:
            continue  # a block without ports (a hand-made one)
        target.blocks.get(name).block_record.set_xdata(APP_ID, [(t.code, t.value) for t in xdata])
    return todo


def ensure_symbol(target: Drawing, name: str) -> str:
    """Define the generated block ``name`` in ``target`` (combiner, full string) and return it.

    The block is rendered from its definition (:func:`~pvsld.symbols.cfe.definitions.get_symbol`)
    and copied with :func:`import_blocks`, so it brings its layers, linetypes and port XDATA. A
    block already in ``target`` is reused.

    Raises:
        KeyError: ``name`` is not a block the definitions can render.
    """
    if name not in target.blocks:
        import_blocks(build_document([get_symbol(name)]), target, [name])
    return name


def ensure_combiner(target: Drawing, n_strings: int) -> str:
    """Define the combiner box for ``n_strings`` strings in ``target`` and return its block name.

    Raises:
        ValueError: ``n_strings`` is outside the supported range.
    """
    name = combiner_name(n_strings)
    if name not in target.blocks:
        from pvsld.symbols.cfe.definitions import combiner_box

        import_blocks(build_document([combiner_box(n_strings)]), target, [name])
    return name
