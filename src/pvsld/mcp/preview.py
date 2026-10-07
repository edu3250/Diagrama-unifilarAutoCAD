"""Shrink the PNG preview until it fits the size budget of an MCP tool result.

The backend writes the A3 sheet at 100 dpi (about 400 KB), which would not fit the host limits once
base64-encoded (Claude Code caps a tool result at 25k tokens, Claude Desktop at about 150k
characters). The copy returned to Claude is a downscaled, palette-quantised PNG: drawings use few
flat colours, so 16 colours at 800 to 1000 px stay legible at a fraction of the size. The full
resolution file stays on disk next to the DXF.
"""

from __future__ import annotations

import io
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "PREVIEW_MAX_BYTES",
    "PREVIEW_MAX_BYTES_ENV",
    "PreviewImage",
    "preview_limit_from_environment",
    "shrink_png",
]

log = logging.getLogger("pvsld.mcp")

# Base64 adds a third: 62 kB become about 83k characters, which leaves about 17k of the 100k
# characters (25k tokens at 4 characters per token) for the text of the result.
PREVIEW_MAX_BYTES = 62_000
PREVIEW_MAX_BYTES_ENV = "PVSLD_PREVIEW_MAX_BYTES"
_WIDTHS = (1000, 900, 800, 700, 600, 500)
_PALETTES = (16, 8)


def preview_limit_from_environment(environ: Mapping[str, str] | None = None) -> int:
    """``$PVSLD_PREVIEW_MAX_BYTES`` when it is a positive integer, else the default.

    The default follows the 25k-token cap of Claude Code at four characters per token. A host that
    counts base64 differently can be given a smaller budget without touching the code.
    """
    raw = (os.environ if environ is None else environ).get(PREVIEW_MAX_BYTES_ENV, "").strip()
    if not raw:
        return PREVIEW_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        value = 0
    if value <= 0:
        log.warning("ignoring %s=%r: expected a positive integer", PREVIEW_MAX_BYTES_ENV, raw)
        return PREVIEW_MAX_BYTES
    return value


@dataclass(frozen=True)
class PreviewImage:
    data: bytes
    width: int
    height: int


def shrink_png(png: bytes, max_bytes: int = PREVIEW_MAX_BYTES) -> PreviewImage | None:
    """Return the largest candidate of at most ``max_bytes``, or ``None`` when none fits.

    Candidates go from wide to narrow and, at each width, from 16 to 8 colours, so the result keeps
    as much resolution as the budget allows. Nothing is upscaled.
    """
    from PIL import Image  # a dependency of matplotlib; imported late like the rest of the preview

    with Image.open(io.BytesIO(png)) as opened:
        # The sheet is drawn on a white background; flatten the alpha channel onto it.
        flat = Image.new("RGB", opened.size, "white")
        flat.paste(opened.convert("RGBA"), mask=opened.convert("RGBA").getchannel("A"))
    for width in _WIDTHS:
        resized = flat
        if width < flat.width:
            height = max(1, round(flat.height * width / flat.width))
            resized = flat.resize((width, height), Image.Resampling.LANCZOS)
        for colours in _PALETTES:
            palette = resized.quantize(
                colors=colours, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
            )
            buffer = io.BytesIO()
            palette.save(buffer, format="PNG", optimize=True)
            if buffer.tell() <= max_bytes:
                return PreviewImage(buffer.getvalue(), resized.width, resized.height)
    return None
