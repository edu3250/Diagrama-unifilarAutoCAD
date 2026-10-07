"""The PNG preview of the A3 sheet (ezdxf drawing add-on + matplotlib Agg)."""

from __future__ import annotations

import io
import time
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from pvsld.backends.dxf import DxfOutput, render_dxf
from pvsld.backends.preview import DEFAULT_DPI, MM_PER_INCH, render_png, write_png
from pvsld.core.layout import build_diagram
from pvsld.core.validation import validate_pv_design
from s1_helpers import load_example

PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")


@pytest.fixture(scope="module")
def output() -> DxfOutput:
    report = validate_pv_design(load_example())
    assert report.spec is not None
    return render_dxf(build_diagram(report.spec, report.derived))


@pytest.fixture(scope="module")
def image(output: DxfOutput) -> Image.Image:
    return Image.open(io.BytesIO(render_png(output.document))).convert("RGB")


def _assert_a3_size(size: tuple[int, int], dpi: int) -> None:
    """Matplotlib truncates the pixel size of a figure, so allow one pixel of rounding."""
    assert abs(size[0] - 420 / MM_PER_INCH * dpi) <= 1
    assert abs(size[1] - 297 / MM_PER_INCH * dpi) <= 1


def test_png_has_the_a3_aspect_at_the_requested_resolution(image: Image.Image) -> None:
    _assert_a3_size(image.size, DEFAULT_DPI)


def test_png_signature_and_dpi_scaling(output: DxfOutput) -> None:
    data = render_png(output.document, dpi=50)
    assert data.startswith(PNG_SIGNATURE)
    _assert_a3_size(Image.open(io.BytesIO(data)).size, 50)


def _dark_fraction(image: Image.Image, box: tuple[float, float, float, float]) -> float:
    """Fraction of non-white pixels in a region of the sheet (millimetres, origin bottom-left)."""
    scale = image.size[0] / 420
    left, bottom, right, top = box
    region = image.crop(
        (
            round(left * scale),
            round((297 - top) * scale),
            round(right * scale),
            round((297 - bottom) * scale),
        )
    )
    pixels = np.asarray(region)
    return float((pixels != 255).any(axis=2).mean())


def test_png_is_not_blank_and_has_a_white_background(image: Image.Image) -> None:
    assert image.getpixel((2, 2)) == (255, 255, 255)
    assert 0.01 < _dark_fraction(image, (0, 0, 420, 297)) < 0.25


@pytest.mark.parametrize(
    ("what", "region"),
    [
        ("title block", (225, 10, 410, 70)),
        ("revision block", (225, 70, 410, 95)),
        ("string table", (15, 115, 203, 140)),
        ("schematic: strings", (20, 190, 60, 260)),
        ("schematic: inverter", (115, 187, 160, 253)),
        ("legend", (225, 100, 405, 140)),
    ],
)
def test_every_part_of_the_sheet_is_drawn(
    image: Image.Image, what: str, region: tuple[float, float, float, float]
) -> None:
    assert _dark_fraction(image, region) > 0.01, f"{what} looks empty"


def test_the_viewport_frame_is_not_drawn_but_the_model_content_is(image: Image.Image) -> None:
    # the inside border corner (non-plot viewport frame) stays white; layer colours show up
    pixels = np.asarray(image).reshape(-1, 3).astype(int)
    red, green, blue = pixels[:, 0], pixels[:, 1], pixels[:, 2]
    assert ((red < 80) & (blue > 200)).any(), "no blue (DC) pixels"
    assert ((red > 200) & (green < 80) & (blue < 80)).any(), "no red (AC) pixels"
    assert ((green > 150) & (red < 100)).any(), "no green (grounding) pixels"


def test_png_preview_renders_in_at_most_three_seconds(output: DxfOutput) -> None:
    render_png(output.document)  # first call imports matplotlib and warms the font cache
    timings = []
    for _ in range(2):
        started = time.perf_counter()
        render_png(output.document)
        timings.append(time.perf_counter() - started)
    assert min(timings) <= 3.0, f"preview took {min(timings):.2f} s"


def test_write_png_creates_the_folder_and_returns_the_bytes(
    output: DxfOutput, tmp_path: Path
) -> None:
    path = tmp_path / "a" / "b" / "sld.png"
    data = write_png(output.document, path, dpi=40)
    assert path.read_bytes() == data
