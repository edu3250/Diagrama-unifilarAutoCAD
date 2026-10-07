"""The preview returned to Claude is shrunk to the size budget and stays a valid PNG."""

from __future__ import annotations

import io
import random

import pytest
from PIL import Image, ImageDraw

from pvsld.mcp.preview import (
    PREVIEW_MAX_BYTES,
    PREVIEW_MAX_BYTES_ENV,
    preview_limit_from_environment,
    shrink_png,
)

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _sheet(width: int = 1654, height: int = 1169) -> bytes:
    """A stand-in for the A3 sheet: white page, coloured lines, a grid of text-like boxes."""
    image = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    for row in range(0, height, 40):
        draw.line([(40, row), (width - 40, row)], fill=(0, 0, 255, 255), width=2)
    for column in range(0, width, 60):
        draw.rectangle([column, 100, column + 30, 900], outline=(255, 0, 0, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _noise(width: int = 300, height: int = 200) -> bytes:
    rng = random.Random(7)
    image = Image.new("RGB", (width, height))
    image.putdata(
        [
            (rng.randrange(256), rng.randrange(256), rng.randrange(256))
            for _ in range(width * height)
        ]
    )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_a_sheet_is_shrunk_below_the_budget() -> None:
    original = _sheet()
    preview = shrink_png(original)
    assert preview is not None
    assert len(preview.data) <= PREVIEW_MAX_BYTES
    assert len(preview.data) < len(original)
    assert preview.data.startswith(PNG_MAGIC)


def test_the_result_is_a_palette_png_of_the_reported_size() -> None:
    preview = shrink_png(_sheet())
    assert preview is not None
    with Image.open(io.BytesIO(preview.data)) as image:
        assert image.size == (preview.width, preview.height)
        assert image.mode == "P"


def test_the_aspect_ratio_is_kept() -> None:
    preview = shrink_png(_sheet(1654, 1169))
    assert preview is not None
    assert preview.width / preview.height == pytest.approx(1654 / 1169, rel=0.01)


def test_the_widest_candidate_that_fits_wins() -> None:
    generous = shrink_png(_sheet(), max_bytes=10_000_000)
    tight = shrink_png(_sheet(), max_bytes=40_000)
    assert generous is not None
    assert tight is not None
    assert generous.width >= tight.width


def test_a_small_image_is_not_upscaled() -> None:
    preview = shrink_png(_sheet(400, 300), max_bytes=10_000_000)
    assert preview is not None
    assert preview.width == 400


def test_transparent_pixels_become_white() -> None:
    preview = shrink_png(_sheet(400, 300), max_bytes=10_000_000)
    assert preview is not None
    with Image.open(io.BytesIO(preview.data)) as image:
        assert image.convert("RGB").getpixel((5, 5)) == (255, 255, 255)


def test_none_is_returned_when_nothing_fits() -> None:
    assert shrink_png(_noise(), max_bytes=1_000) is None


def test_the_budget_defaults_to_the_constant() -> None:
    assert preview_limit_from_environment({}) == PREVIEW_MAX_BYTES
    assert preview_limit_from_environment({PREVIEW_MAX_BYTES_ENV: "  "}) == PREVIEW_MAX_BYTES


def test_the_budget_can_be_set_by_environment() -> None:
    assert preview_limit_from_environment({PREVIEW_MAX_BYTES_ENV: "30000"}) == 30_000


@pytest.mark.parametrize("raw", ["abc", "0", "-5", "1.5"])
def test_a_bad_budget_is_ignored_with_a_warning(raw: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level("WARNING", logger="pvsld.mcp"):
        assert preview_limit_from_environment({PREVIEW_MAX_BYTES_ENV: raw}) == PREVIEW_MAX_BYTES
    assert PREVIEW_MAX_BYTES_ENV in caplog.text


def test_the_budget_is_read_from_the_process_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(PREVIEW_MAX_BYTES_ENV, "45000")
    assert preview_limit_from_environment() == 45_000
