"""Spike S2 benchmark harness: build the plug-in, run the AutoCAD suite, report against Stage 2.2.

Usage (Windows, licensed AutoCAD 2027, repo virtual environment):

    python scripts/s2_bench.py              # full run (about 10-15 min), writes build/s2/
    python scripts/s2_bench.py --quick      # smaller samples, a few minutes
    python scripts/s2_bench.py --report build/s2/results.json   # re-render a past run

The run starts its own AutoCAD (never one that is already open), NETLOADs the plug-in (the
owner may have to answer AutoCAD's unsigned-DLL dialog with "Load once"), and quits AutoCAD at
the end without saving. See docs/spikes/s2-autocad-connectivity.md.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SOLUTION = REPO / "plugin" / "PvSld.AutoCAD.slnx"
QUICK = {
    "PVSLD_S2_PING_SAMPLES": "50",
    "PVSLD_S2_OP_SAMPLES": "10",
    "PVSLD_S2_BATCH_REPEATS": "2",
    "PVSLD_S2_RUNS": "10",
    "PVSLD_S2_COM_RUNS": "5",
}


def build_plugin() -> None:
    subprocess.run(["dotnet", "build", str(SOLUTION), "-c", "Release", "--nologo"], check=True)


def run_suite(results: Path, *, quick: bool, extra: list[str]) -> int:
    env = {**os.environ, "PVSLD_S2_RESULTS": str(results)}
    if quick:
        env.update(QUICK)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "tests/autocad",
        "--run-autocad",
        "-s",
        "-p",
        "no:cacheprovider",
        "-o",
        "addopts=-ra",
        *extra,
    ]
    return subprocess.run(command, cwd=REPO, env=env, check=False).returncode


def _get(data: dict[str, Any], *path: str) -> Any:
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return None
        data = data[key]
    return data


def _ms(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.1f} ms"


def _ratio(com: float | None, plugin: float | None) -> str:
    if not com or not plugin:
        return "n/a"
    return f"{com / plugin:.1f}x"


def _verdict(ok: bool | None) -> str:
    return "n/a" if ok is None else ("PASS" if ok else "FAIL")


def render(data: dict[str, Any]) -> str:
    com, plugin, busy, safety = (data.get(k, {}) for k in ("com", "plugin", "busy", "safety"))
    ping_t = _get(plugin, "ping_transport", "p95_ms")
    ping_m = _get(plugin, "ping_main_thread", "p95_ms")
    batch_max = _get(plugin, "batch_200_200", "max_ms")
    reliability = plugin.get("reliability", {})
    com_reliability = com.get("reliability", {})
    injected = safety.get("injected_failure", [])
    unauth = safety.get("unauthenticated", {})
    pipe_acl = safety.get("pipe_acl", {})

    rows = [
        (
            "Plug-in ping p95 < 50 ms",
            f"transport {_ms(ping_t)}; via main thread {_ms(ping_m)}",
            _verdict(None if ping_m is None else max(ping_t, ping_m) < 50),
        ),
        (
            "200 attributed inserts + 200 lines < 2 s",
            f"max {_ms(batch_max)} (p50 {_ms(_get(plugin, 'batch_200_200', 'p50_ms'))}); "
            f"COM p50 {_ms(_get(com, 'batch_200_200', 'p50_ms'))}",
            _verdict(None if batch_max is None else batch_max < 2000),
        ),
        (
            "100/100 consecutive runs without unhandled errors",
            f"plug-in {reliability.get('runs', 0) - reliability.get('failures', 0)}/"
            f"{reliability.get('runs', 0)}; COM baseline "
            f"{com_reliability.get('runs', 0) - com_reliability.get('failures', 0)}/"
            f"{com_reliability.get('runs', 0)}",
            _verdict(
                None
                if not reliability
                else reliability["failures"] == 0 and reliability["runs"] >= 100
            ),
        ),
    ]
    for key, label in (
        ("modal_dialog", "modal dialog"),
        ("command_running", "running command"),
        ("command_waiting_for_input", "command waiting for input"),
    ):
        record = busy.get(key)
        if record:
            p = record["plugin"]
            rows.append(
                (
                    f"Busy ({label}) -> actionable error <= 5 s, no hang",
                    f"{p['outcome']} '{p.get('reason', '')}' in {p['seconds']:.2f} s; recovered "
                    f"{record['recovered']} ({record['recovery_s']} s); "
                    f"COM {record['com']['outcome']} "
                    f"after {record['com']['seconds']:.2f} s",
                    _verdict(p["outcome"] == "busy" and p["seconds"] <= 5 and record["recovered"]),
                )
            )
    rows += [
        (
            "Injected mid-transaction failure leaves drawing unchanged",
            f"{sum(1 for r in injected if r['unchanged'] and r['com_count_unchanged'])}/"
            f"{len(injected)} cases unchanged (plug-in digest and COM count)",
            _verdict(
                None
                if not injected
                else all(r["unchanged"] and r["com_count_unchanged"] for r in injected)
            ),
        ),
        (
            "Client without the secret refused; pipe ACL current user only",
            f"no-auth error {_get(unauth, 'no_auth_error', 'code')}, closed "
            f"{unauth.get('connection_closed')}; ACL "
            f"{[(a['type'], a['sid']) for a in pipe_acl.get('aces', [])]}",
            _verdict(
                None
                if not unauth
                else unauth.get("connection_closed")
                and _get(unauth, "no_auth_error", "code") == -32001
            ),
        ),
    ]

    ratios = [
        (
            "ping (one round trip)",
            _get(com, "ping", "p50_ms"),
            _get(plugin, "ping_main_thread", "p50_ms"),
        ),
        (
            "insert attributed block",
            _get(com, "insert_block", "p50_ms"),
            _get(plugin, "insert_block", "p50_ms"),
        ),
        (
            "read attributes",
            _get(com, "read_attributes", "p50_ms"),
            _get(plugin, "read_attributes", "p50_ms"),
        ),
        (
            "batch 200 + 200",
            _get(com, "batch_200_200", "p50_ms"),
            _get(plugin, "batch_200_200", "p50_ms"),
        ),
    ]
    lines = [
        "| Stage 2.2 criterion | Measured | Result |",
        "|---|---|---|",
        *(f"| {a} | {b} | {c} |" for a, b, c in rows),
        "",
        "| Operation (p50) | COM | Plug-in | COM / plug-in |",
        "|---|---|---|---|",
        *(f"| {name} | {_ms(c)} | {_ms(p)} | {_ratio(c, p)} |" for name, c, p in ratios),
    ]
    autocad = data.get("autocad", {})
    lines += [
        "",
        f"AutoCAD {autocad.get('version', '?')} pid {autocad.get('pid', '?')}, started in "
        f"{autocad.get('startup_s', '?')} s, COM binding {autocad.get('com_binding', '?')}; "
        f"plug-in load {_get(data, 'plugin_load', 'seconds')} s, trust dialogs "
        f"{_get(data, 'plugin_load', 'trust_dialogs')}; "
        f"shutdown {_get(autocad, 'shutdown', 'note')}.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--quick", action="store_true", help="smaller samples (smoke run)")
    parser.add_argument("--no-build", action="store_true", help="skip dotnet build")
    parser.add_argument("--results", type=Path, default=REPO / "build" / "s2" / "results.json")
    parser.add_argument(
        "--report", type=Path, help="only render the report of an existing results file"
    )
    parser.add_argument("pytest_args", nargs="*", help="extra arguments for pytest (after --)")
    args = parser.parse_args(argv)

    if args.report:
        print(render(json.loads(args.report.read_text(encoding="utf-8"))))
        return 0
    if sys.platform != "win32":
        parser.error("the S2 benchmark needs Windows and a licensed AutoCAD 2027")
    if not args.no_build:
        build_plugin()
    code = run_suite(args.results, quick=args.quick, extra=args.pytest_args)
    if args.results.exists():
        report = render(json.loads(args.results.read_text(encoding="utf-8")))
        args.results.with_suffix(".md").write_text(report + "\n", encoding="utf-8")
        print("\n" + report)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
