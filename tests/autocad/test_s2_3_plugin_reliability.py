"""S2 reliability: 100 consecutive full runs through the plug-in without an unhandled error."""

from __future__ import annotations

import time

import pytest
from s2_support import BLOCK, Results, env_int, inserts, lines

pytestmark = pytest.mark.autocad


def test_consecutive_runs_without_errors(bridge, plugin_drawing: str, results: Results) -> None:
    runs = env_int("PVSLD_S2_RUNS", 100)
    failures: list[str] = []
    durations = []
    for run in range(runs):
        started = time.perf_counter()
        try:
            bridge.ping(main_thread=True)
            values = {"COMP_ID": f"R-{run}", "LABEL": "Interruptor", "RATING": "2x20 A"}
            handle = bridge.insert_block(
                BLOCK, [run * 25.0, 2000], values, document=plugin_drawing
            )["handle"]
            assert (
                bridge.read_attributes(handle=handle, document=plugin_drawing)[0]["attributes"]
                == values
            )
            before = bridge.drawing_stats(document=plugin_drawing)["modelspace_entities"]
            row = 3000.0 + 100.0 * run
            batch = bridge.batch(
                BLOCK, inserts(200, row=row), lines(200, row=row), document=plugin_drawing
            )
            after = bridge.drawing_stats(document=plugin_drawing)["modelspace_entities"]
            assert after - before == 400
            assert (
                bridge.read_attributes(handle=batch["handles"][-1], document=plugin_drawing)[0][
                    "attributes"
                ]["COMP_ID"]
                == "PV-199"
            )
        except Exception as exc:
            failures.append(f"run {run}: {type(exc).__name__}: {exc}")
        durations.append(time.perf_counter() - started)

    results.section("plugin")["reliability"] = {
        "runs": runs,
        "failures": len(failures),
        "first_failures": failures[:5],
        "seconds": round(sum(durations), 1),
        "slowest_run_s": round(max(durations), 3),
        "run": "main-thread ping + insert + read-back + batch 200/200 + count and read-back checks",
    }
    assert failures == []
