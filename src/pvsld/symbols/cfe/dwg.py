"""The symbol library as a DWG 2018 (Stage 4.4): export with the Core Console and a staleness check.

``symbols/pvsld-symbols.dwg`` is the DXF library saved by AutoCAD (TrustedDWG, AUDIT 0/0). The DXF
stays the source of truth; ``symbols/pvsld-symbols.dwg.json`` records the SHA-256 of the DXF and the
library version the DWG was made from, so a CI test fails when the DXF changes and the DWG is not
exported again. Exporting needs a licensed AutoCAD; checking does not.
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pvsld.backends.base import sha256_hex
from pvsld.finishers.core_console import FinishOptions, finish
from pvsld.finishers.outputs import inspect_dwg
from pvsld.symbols.cfe.build import LIBRARY_FILE
from pvsld.symbols.cfe.model import LIBRARY_VERSION

DWG_FILE = Path("symbols") / "pvsld-symbols.dwg"
DWG_RELEASE = "AC1032"
"""DWG 2018 (AutoCAD 2018-2027)."""


def manifest_path(dwg: Path) -> Path:
    return dwg.with_name(dwg.name + ".json")


@dataclass(frozen=True)
class DwgExport:
    dwg: Path
    manifest: Path
    audit: tuple[int, int]


class LibraryDwgError(RuntimeError):
    """The export failed; the message says why."""


def export_dwg(
    dxf: Path = LIBRARY_FILE, dwg: Path = DWG_FILE, *, timeout_s: float = 180
) -> DwgExport:
    """Save ``dxf`` as the DWG 2018 ``dwg`` with the Core Console and write its manifest.

    Raises:
        LibraryDwgError: Core Console is missing or failed, AUDIT found errors, or the DWG is not
            a TrustedDWG 2018.
    """
    from pvsld.finishers.core_console import FinisherError

    source_bytes = dxf.read_bytes()
    with tempfile.TemporaryDirectory() as work:
        source = Path(work) / f"{dwg.stem}.dxf"  # the DWG takes the name of what Core Console opens
        source.write_bytes(source_bytes)
        try:
            result = finish(
                source,
                Path(work),
                options=FinishOptions(pdf=False, timeout_s=timeout_s, overwrite=True),
            )
        except FinisherError as error:
            raise LibraryDwgError(str(error)) from error
        audit = result.audit
        if not result.ok or audit is None:
            raise LibraryDwgError("; ".join(result.problems) or "Core Console did not finish")
        if (audit.errors_found, audit.errors_fixed) != (0, 0):
            raise LibraryDwgError(f"AUDIT found {audit.errors_found} errors")
        dwg.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(result.paths.dwg, dwg)
    problems = check_dwg_file(dwg)
    if problems:
        raise LibraryDwgError("; ".join(problems))
    manifest = manifest_path(dwg)
    manifest.write_text(
        json.dumps(
            {
                "library_version": LIBRARY_VERSION,
                "dxf_sha256": sha256_hex(source_bytes),
                "dwg_release": DWG_RELEASE,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return DwgExport(dwg=dwg, manifest=manifest, audit=(0, 0))


def check_dwg_file(dwg: Path) -> list[str]:
    """Problems of the DWG itself: missing, not DWG 2018, not saved by AutoCAD."""
    if not dwg.is_file():
        return [f"{dwg} is missing: run `pvsld symbols dwg` (needs AutoCAD) and commit it"]
    info = inspect_dwg(dwg)
    problems = []
    if info.version != DWG_RELEASE:
        problems.append(f"{dwg} is {info.version}, expected {DWG_RELEASE} (DWG 2018)")
    if not info.trusted:
        problems.append(f"{dwg} was not last saved by AutoCAD (no TrustedDWG notice)")
    return problems


def check_dwg(dxf: Path = LIBRARY_FILE, dwg: Path = DWG_FILE) -> list[str]:
    """Problems of the committed DWG against the DXF it must have been exported from."""
    problems = check_dwg_file(dwg)
    if problems:
        return problems
    manifest = manifest_path(dwg)
    if not manifest.is_file():
        return [f"{manifest} is missing: run `pvsld symbols dwg`"]
    recorded = json.loads(manifest.read_text(encoding="utf-8"))
    if recorded.get("dxf_sha256") != sha256_hex(dxf.read_bytes()):
        problems.append(f"{dwg} is stale: {dxf} changed since; run `pvsld symbols dwg`")
    if recorded.get("library_version") != LIBRARY_VERSION:
        problems.append(
            f"{dwg} is library {recorded.get('library_version')}, the definitions are "
            f"{LIBRARY_VERSION}; run `pvsld symbols dwg`"
        )
    return problems
