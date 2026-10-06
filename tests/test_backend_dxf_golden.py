"""Golden-file test: the DXF of the sample is byte-identical across runs, processes and platforms.

The committed fixture ``tests/golden/residential_7p7kwp.dxf`` is compared by SHA-256. Its bytes are
produced with ezdxf fixed metadata and explicit LF newlines, and ``.gitattributes`` marks ``*.dxf``
as ``-text``, so a Windows and a Linux checkout hold the same bytes and the CI matrix (Windows and
Ubuntu) proves the cross-platform claim.

When a deliberate change to the drawing makes this test fail, regenerate the fixture::

    pvsld generate examples/residential_7p7kwp.yaml -o tests/golden/residential_7p7kwp.dxf

and review the diff of the file in the pull request.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import ezdxf
import pytest

from pvsld.backends.base import sha256_hex
from pvsld.backends.dxf import render_dxf
from pvsld.backends.readback import verify
from pvsld.core.layout import build_diagram
from pvsld.core.validation import validate_pv_design
from s1_helpers import EXAMPLE, GOLDEN_DIR, ROOT, load_example

GOLDEN = GOLDEN_DIR / "residential_7p7kwp.dxf"
REGENERATE = (
    "pvsld generate examples/residential_7p7kwp.yaml -o tests/golden/residential_7p7kwp.dxf"
)


def _generate() -> bytes:
    report = validate_pv_design(load_example())
    assert report.spec is not None
    return render_dxf(build_diagram(report.spec, report.derived)).data


def test_the_golden_fixture_exists_and_has_lf_newlines_only() -> None:
    data = GOLDEN.read_bytes()
    assert data.startswith(b"  0\nSECTION\n")
    assert b"\r" not in data, "the golden file was checked out with CRLF; check .gitattributes"


def test_generated_bytes_match_the_golden_sha256() -> None:
    expected = sha256_hex(GOLDEN.read_bytes())
    actual = sha256_hex(_generate())
    assert actual == expected, (
        f"the generated DXF differs from the golden fixture\n"
        f"  golden    sha256 {expected}\n  generated sha256 {actual}\n"
        f"  ezdxf {ezdxf.__version__}\n"
        f"If the change is intended, regenerate the fixture with:\n  {REGENERATE}"
    )


def test_generated_bytes_equal_the_golden_file_byte_for_byte() -> None:
    assert _generate() == GOLDEN.read_bytes()


def test_the_golden_fixture_itself_passes_every_read_back_check() -> None:
    report = validate_pv_design(load_example())
    assert report.spec is not None
    readback = verify(build_diagram(report.spec, report.derived), GOLDEN.read_bytes())
    assert readback.problems == ()
    assert readback.ok


# Seeds 0 and 1 happened to give one CLASS order and 7 and 4242 the other before the fix.
@pytest.mark.parametrize("hash_seed", ["0", "1", "7", "4242"])
def test_a_separate_process_with_another_hash_seed_gives_the_same_bytes(
    tmp_path: Path, hash_seed: str
) -> None:
    """Set and dict iteration order must not leak into the file (PYTHONHASHSEED varies it)."""
    output = tmp_path / "sld.dxf"
    env = {**os.environ, "PYTHONHASHSEED": hash_seed, "PYTHONUTF8": "1"}
    completed = subprocess.run(
        [sys.executable, "-m", "pvsld.cli", "generate", str(EXAMPLE), "-o", str(output)],
        capture_output=True,
        text=True,
        env=env,
        cwd=ROOT,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert sha256_hex(output.read_bytes()) == sha256_hex(GOLDEN.read_bytes())


def test_gitattributes_keeps_dxf_files_byte_exact() -> None:
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines()
    assert "*.dxf -text" in attributes
