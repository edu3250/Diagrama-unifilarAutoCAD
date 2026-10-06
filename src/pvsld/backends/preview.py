"""PNG preview of a rendered drawing, through the ezdxf drawing add-on and matplotlib (Agg).

The preview is for Claude's visual self-check and for human review, not for plotting: ezdxf
approximates fonts and text metrics (ADR-0001, Consequences). It renders the A3 paper-space layout,
so the viewport, border, title block and the model content all appear as on the sheet.

Speed. ezdxf draws every text as filled glyph paths, and ``Axes.add_patch`` recomputes the Bezier
extents of each one to update the data limits: about 10 s for the 300 texts of a sheet. The sheet
size is known, so :class:`_SheetBackend` adds the artists without that bookkeeping and the caller
sets the limits; the same sheet then renders in well under a second.

``matplotlib`` is imported lazily, so commands that do not need a preview start fast.
"""

from __future__ import annotations

import io
from collections.abc import Iterable
from pathlib import Path
from typing import TYPE_CHECKING

from ezdxf.document import Drawing

from pvsld.backends.dxf import LAYOUT_NAME

if TYPE_CHECKING:
    from ezdxf.addons.drawing.backend import BackendProperties
    from ezdxf.path import Path2d

DEFAULT_DPI = 100
MM_PER_INCH = 25.4


def _sheet_backend_class() -> type:
    """Build the fast backend class (needs matplotlib, hence created on first use)."""
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from ezdxf.npshapes import to_matplotlib_path
    from matplotlib.patches import PathPatch

    class _SheetBackend(MatplotlibBackend):  # type: ignore[misc]
        """``MatplotlibBackend`` without the per-patch data-limit updates."""

        def draw_path(self, path: Path2d, properties: BackendProperties) -> None:
            try:
                patch = PathPatch(
                    to_matplotlib_path([path]),
                    linewidth=self.get_lineweight(properties),
                    fill=False,
                    color=properties.color,
                    zorder=self._get_z(),
                )
            except ValueError:
                return
            self.ax.add_artist(patch)

        def draw_filled_paths(self, paths: Iterable[Path2d], properties: BackendProperties) -> None:
            # Hole detection is skipped: the sheet has no hatches, and glyph outlines keep the
            # winding of the font, so the non-zero fill already renders counters (O, A, D, P).
            try:
                patch = PathPatch(
                    to_matplotlib_path(paths, detect_holes=False),
                    color=properties.color,
                    linewidth=0,
                    fill=True,
                    zorder=self._get_z(),
                )
            except ValueError:
                return
            self.ax.add_artist(patch)

        def finalize(self) -> None:
            """Keep the limits the caller set: do not autoscale to the data."""

    return _SheetBackend


def render_png(document: Drawing, *, dpi: int = DEFAULT_DPI) -> bytes:
    """Render the A3 layout of ``document`` to PNG bytes (white background, layer colours)."""
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    layout = document.layouts.get(LAYOUT_NAME)
    width_mm = float(layout.dxf_layout.dxf.paper_width)
    height_mm = float(layout.dxf_layout.dxf.paper_height)

    figure = Figure(figsize=(width_mm / MM_PER_INCH, height_mm / MM_PER_INCH), dpi=dpi)
    FigureCanvasAgg(figure)
    axes = figure.add_axes((0, 0, 1, 1))
    axes.set_xlim(0, width_mm)
    axes.set_ylim(0, height_mm)
    axes.set_axis_off()
    config = Configuration(
        background_policy=BackgroundPolicy.WHITE,
        color_policy=ColorPolicy.COLOR,
    )
    backend = _sheet_backend_class()(axes)
    Frontend(RenderContext(document), backend, config=config).draw_layout(layout, finalize=True)
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", dpi=dpi, facecolor="white")
    return buffer.getvalue()


def write_png(document: Drawing, path: Path, *, dpi: int = DEFAULT_DPI) -> bytes:
    """Render the preview and write it to ``path`` (parent folders are created)."""
    data = render_png(document, dpi=dpi)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
