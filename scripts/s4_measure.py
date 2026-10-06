"""Spike S4 measurements: the Core Console finisher on the S1 sample (Stage 2.4).

Run on the licensed workstation from the repository root::

    .venv\\Scripts\\python scripts/s4_measure.py [--runs 5] [--timeout 120]

Everything happens under ``out/s4/measure`` (git-ignored), which is recreated first. The script

1. generates the S1 sheet from ``examples/residential_7p7kwp.yaml`` and checks it is byte-identical
   to the golden DXF;
2. finishes it ``--runs`` times in one folder (DWG 2018 + PDF), the first run cold;
3. repeats the AUDIT on a copy whose overall paper-space viewport is on layer ``0`` (the S1 fix
   AutoCAD's AUDIT asks for);
4. re-opens the produced DWG in Core Console (AUDIT only) to show it loads cleanly;
5. tries the variants: an output folder with a space, ``DXFIN`` instead of ``/i``, and a detailed
   plot with an explicit paper;
6. checks the failure modes: invalid input, missing Core Console, a 1 s timeout, a missing PC3;
7. inspects the DWG and the PDF (version, TrustedDWG text, product information, educational or
   non-commercial wording) and writes ``results.json``.

Only processes this script starts are ever stopped (on their own timeout).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import re
import shutil
import statistics
import subprocess
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from pvsld.finishers.core_console import (
    FinisherError,
    FinishOptions,
    FinishResult,
    find_accoreconsole,
    finish,
)
from pvsld.finishers.outputs import MARKING_WORDS
from pvsld.service import generate_single_line_diagram

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples" / "residential_7p7kwp.yaml"
GOLDEN = ROOT / "tests" / "golden" / "residential_7p7kwp.dxf"
OUT = ROOT / "out" / "s4" / "measure"
LIMIT_S = 15.0
FULL_BLEED_A3 = "ISO full bleed A3 (420.00 x 297.00 MM)"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _summary(result: FinishResult) -> dict[str, Any]:
    data = result.to_dict()
    data["console_lines"] = len(result.log.text.splitlines())
    return data


def _copy(source: Path, folder: Path, name: str = "sld.dxf") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / name
    shutil.copyfile(source, target)
    return target


def _viewport_on_layer_zero(source: Path, target: Path) -> int:
    """Copy ``source`` with the overall paper-space VIEWPORT (id 1) moved to layer ``0``."""
    data = source.read_bytes()
    pattern = re.compile(rb"(\n  0\nVIEWPORT\n(?:(?!\n  0\n).)*?\n  8\n)([^\n]+)(\n)", re.DOTALL)
    changed = 0

    def _fix(match: re.Match[bytes]) -> bytes:
        nonlocal changed
        entity_end = data.find(b"\n  0\n", match.end())
        if b"\n 69\n1\n" not in data[match.start() : entity_end]:
            return match.group(0)
        changed += 1
        return match.group(1) + b"0" + match.group(3)

    target.write_bytes(pattern.sub(_fix, data))
    return changed


def _process_alive(pid: int | None) -> bool | None:
    if pid is None or sys.platform != "win32":
        return None
    listing = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True, check=False
    )
    return str(pid) in listing.stdout


def _markings_in_log(result: FinishResult) -> list[str]:
    lowered = result.log.text.lower()
    return [word for word in MARKING_WORDS if word in lowered]


def _measure(label: str, action: Callable[[], FinishResult]) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = action()
    except FinisherError as error:
        wall = round(time.perf_counter() - started, 3)
        print(f"[{label}] refused before start: {error} ({wall} s)")
        return {"label": label, "refused": str(error), "wall_s": wall}
    data = _summary(result)
    data["label"] = label
    data["log_markings"] = _markings_in_log(result)
    status = "OK" if result.ok else "FAILED"
    audit = result.audit
    audit_text = "n/a" if audit is None else f"{audit.errors_found}/{audit.errors_fixed}"
    print(f"[{label}] {status} in {result.duration_s} s; audit {audit_text}; {result.step_ms}")
    for problem in result.problems:
        print(f"    problem: {problem}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    executable = find_accoreconsole()
    if executable is None:
        print("accoreconsole.exe not found; S4 needs a licensed full AutoCAD", file=sys.stderr)
        return 2
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    results: dict[str, Any] = {
        "date": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "machine": {
            "os": platform.platform(),
            "python": platform.python_version(),
            "accoreconsole": str(executable),
            "accoreconsole_size": executable.stat().st_size,
        },
        "limit_s": LIMIT_S,
    }

    # 1. Generate the sheet through the S1 pipeline and compare with the golden file.
    sheet_dir = OUT / "sheet"
    sheet_dir.mkdir()
    spec = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    generated = generate_single_line_diagram(spec, sheet_dir / "sld.dxf")
    results["generate"] = {
        "ok": generated.ok,
        "sha256": generated.sha256,
        "golden_sha256": _sha256(GOLDEN),
        "identical_to_golden": generated.sha256 == _sha256(GOLDEN),
    }
    print(
        f"generate: ok={generated.ok}, identical to golden: {generated.sha256 == _sha256(GOLDEN)}"
    )
    sheet = sheet_dir / "sld.dxf"
    timeout = args.timeout

    # 2. Timed runs, all in one folder (the first one creates the /isolate profile).
    runs_dir = OUT / "runs"
    source = _copy(sheet, runs_dir)
    options = FinishOptions(timeout_s=timeout, overwrite=True)
    runs = [
        _measure(f"run {n}", lambda: finish(source, options=options))
        for n in range(1, args.runs + 1)
    ]
    durations = [run["duration_s"] for run in runs if run.get("duration_s") is not None]
    results["runs"] = runs
    results["timing"] = {
        "first_s": durations[0] if durations else None,
        "median_s": round(statistics.median(durations), 3) if durations else None,
        "max_s": max(durations) if durations else None,
        "warm_median_s": round(statistics.median(durations[1:]), 3) if len(durations) > 1 else None,
        "all_within_limit": bool(durations) and max(durations) <= LIMIT_S,
    }
    print(f"timing: {results['timing']}")

    # 3. The S1 fix AutoCAD asks for: overall paper-space viewport on layer 0.
    fixed_dir = OUT / "vport-layer0"
    fixed_dir.mkdir()
    fixed = fixed_dir / "sld.dxf"
    changed = _viewport_on_layer_zero(sheet, fixed)
    results["vport_layer0"] = {
        "viewports_changed": changed,
        **_measure("viewport on layer 0", lambda: finish(fixed, options=options)),
    }

    # 4. Re-open the produced DWGs (AUDIT only): they must load without any notice.
    audit_only = FinishOptions(dwg=False, pdf=False, timeout_s=timeout)
    dwg_copy = _copy(runs_dir / "sld.dwg", OUT / "reopen", "sld.dwg")
    results["reopen_dwg"] = _measure("re-open DWG", lambda: finish(dwg_copy, options=audit_only))
    clean_copy = _copy(fixed_dir / "sld.dwg", OUT / "reopen-layer0", "sld.dwg")
    results["reopen_dwg_layer0"] = _measure(
        "re-open DWG (viewport on layer 0)", lambda: finish(clean_copy, options=audit_only)
    )

    # 5. Variants.
    spaced = _copy(sheet, OUT / "with space")
    results["variant_space"] = _measure(
        "folder with a space", lambda: finish(spaced, options=options)
    )
    dxfin = _copy(sheet, OUT / "dxfin")
    results["variant_dxfin"] = _measure(
        "DXFIN instead of /i",
        lambda: finish(dxfin, options=FinishOptions(open_mode="dxfin", timeout_s=timeout)),
    )
    paper = _copy(sheet, OUT / "paper")
    results["variant_paper"] = _measure(
        f"detailed plot, {FULL_BLEED_A3}",
        lambda: finish(paper, options=FinishOptions(paper=FULL_BLEED_A3, timeout_s=timeout)),
    )

    # 6. Failure modes: each must be reported, never a silent success.
    invalid = OUT / "invalid" / "broken.dxf"
    invalid.parent.mkdir()
    invalid.write_text("0\nSECTION\n2\nHEADER\nthis is not a DXF\n", encoding="ascii")
    results["fail_invalid_input"] = _measure(
        "invalid input", lambda: finish(invalid, options=FinishOptions(timeout_s=timeout))
    )
    results["fail_missing_core_console"] = _measure(
        "missing Core Console",
        lambda: finish(sheet, accoreconsole=OUT / "no-such" / "accoreconsole.exe"),
    )
    slow = _copy(sheet, OUT / "timeout")
    timed = _measure("1 s timeout", lambda: finish(slow, options=FinishOptions(timeout_s=1.0)))
    timed["pid_alive_after"] = _process_alive(timed.get("pid"))
    results["fail_timeout"] = timed
    no_pc3 = _copy(sheet, OUT / "missing-pc3")
    results["fail_missing_pc3"] = _measure(
        "missing PC3 (no PDF)",
        lambda: finish(no_pc3, options=FinishOptions(plotter="NoSuch.pc3", timeout_s=timeout)),
    )

    path = OUT / "results.json"
    path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"results: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
