"""Import blocks of the symbol library DXF into another drawing (what Stage 4.3 needs).

ezdxf's :class:`~ezdxf.addons.Importer` copies a block with its entities, layers, linetypes and
text styles, but not the XDATA of the block record, which is where ADR-0003 keeps the ports. The
generator would then place symbols whose ports a reader cannot find. :func:`import_blocks` copies
the block XDATA as well, so an imported block is indistinguishable from the library's.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import ezdxf
from ezdxf.addons import Importer
from ezdxf.document import Drawing
from ezdxf.lldxf.const import DXFValueError

from pvsld.symbols.cfe.build import build_document
from pvsld.symbols.cfe.definitions import combiner_box, combiner_name
from pvsld.symbols.cfe.model import APP_ID, BLOCK_PREFIX


def load_library(path: Path) -> Drawing:
    """Read the library DXF at ``path``."""
    return ezdxf.readfile(path)


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


def ensure_combiner(target: Drawing, n_strings: int) -> str:
    """Define the combiner box for ``n_strings`` strings in ``target`` and return its block name.

    The block is rendered from :func:`~pvsld.symbols.cfe.definitions.combiner_box` and copied with
    :func:`import_blocks`, so it brings its layers, linetypes and port XDATA. A block already in
    ``target`` is reused.

    Raises:
        ValueError: ``n_strings`` is outside the supported range.
    """
    name = combiner_name(n_strings)
    if name not in target.blocks:
        import_blocks(build_document([combiner_box(n_strings)]), target, [name])
    return name
