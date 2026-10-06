"""Helpers for the S2 AutoCAD tests: statistics, results file, scratch geometry, dialogs."""

from __future__ import annotations

import json
import os
import platform
import statistics
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DLL = REPO_ROOT / "plugin/src/PvSld.AutoCAD/bin/Release/net10.0-windows/PvSld.AutoCAD.dll"
BLOCK = "PVSLD_S2_TEST"


def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


def env_float(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def percentile(sorted_values: list[float], q: float) -> float:
    """Nearest-rank percentile (``q`` in 0..100) of an already sorted list."""
    if not sorted_values:
        raise ValueError("no samples")
    rank = max(1, round(q / 100 * len(sorted_values) + 0.4999))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def summarize(samples_ms: list[float]) -> dict[str, float]:
    ordered = sorted(samples_ms)
    return {
        "n": len(ordered),
        "min_ms": round(ordered[0], 3),
        "p50_ms": round(percentile(ordered, 50), 3),
        "p95_ms": round(percentile(ordered, 95), 3),
        "p99_ms": round(percentile(ordered, 99), 3),
        "max_ms": round(ordered[-1], 3),
        "mean_ms": round(statistics.fmean(ordered), 3),
    }


def time_calls(fn: Callable[[], Any], count: int) -> list[float]:
    """Wall-clock milliseconds of ``count`` sequential calls."""
    samples = []
    for _ in range(count):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def inserts(count: int, *, row: float = 0.0, prefix: str = "PV") -> list[dict[str, Any]]:
    return [
        {
            "position": [i * 25.0, row],
            "attributes": {"COMP_ID": f"{prefix}-{i}", "LABEL": f"Módulo {i}", "RATING": "550 W"},
        }
        for i in range(count)
    ]


def lines(count: int, *, row: float = 0.0) -> list[dict[str, Any]]:
    return [
        {"start": [i * 25.0, row - 15.0], "end": [i * 25.0 + 20.0, row - 15.0]}
        for i in range(count)
    ]


def wait_until(predicate: Callable[[], bool], timeout: float, interval: float = 0.2) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return predicate()


class Results:
    """Measurements collected during the session, written as JSON at the end."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = {
            "spike": "S2 AutoCAD 2027 connectivity",
            "started_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "machine": {
                "os": platform.platform(),
                "python": platform.python_version(),
                "cpu": platform.processor(),
            },
        }

    def section(self, name: str) -> dict[str, Any]:
        return self.data.setdefault(name, {})

    def save(self) -> None:
        self.data["finished_utc"] = datetime.now(UTC).isoformat(timespec="seconds")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), encoding="utf-8")


def press_escape(pid: int) -> bool:
    """Last resort to cancel a command in *our* AutoCAD: post Esc to its main frame window."""
    import win32con
    import win32gui

    from pvsld.transports.com import process_windows

    frames = [w for w in process_windows(pid) if w.class_name.startswith("AfxMDIFrame")]
    for frame in frames:
        win32gui.PostMessage(frame.hwnd, win32con.WM_KEYDOWN, win32con.VK_ESCAPE, 0)
        win32gui.PostMessage(frame.hwnd, win32con.WM_KEYUP, win32con.VK_ESCAPE, 0)
    return bool(frames)


def click_default_button(hwnd: int) -> None:
    """Close one of *our* test dialogs by pressing its first push button (OK/Aceptar)."""
    import win32con
    import win32gui

    buttons: list[int] = []

    def visit(child: int, _: Any) -> bool:
        if win32gui.GetClassName(child) == "Button":
            buttons.append(child)
        return True

    win32gui.EnumChildWindows(hwnd, visit, None)
    if buttons:
        win32gui.PostMessage(buttons[0], win32con.BM_CLICK, 0, 0)
    else:
        win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
