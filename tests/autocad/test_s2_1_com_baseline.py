"""S2 COM baseline (ADR-0001 O3): the same operations through pywin32, measured, not judged.

Runs before the plug-in is loaded, in its own scratch drawing.
"""

from __future__ import annotations

import time

import pytest
from s2_support import BLOCK, Results, env_int, inserts, lines, summarize, time_calls

pytestmark = pytest.mark.autocad


def test_com_ping_latency(acad, results: Results) -> None:
    samples = time_calls(acad.ping, env_int("PVSLD_S2_PING_SAMPLES", 200))

    results.section("com")["ping"] = summarize(samples)


def test_com_insert_and_read_back(acad, com_drawing: str, results: Results) -> None:
    count = env_int("PVSLD_S2_OP_SAMPLES", 50)
    acad.insert_block(com_drawing, BLOCK, [0, 500])  # create the block definition first
    insert_ms, read_ms = [], []
    for i in range(count):
        values = {"COMP_ID": f"COM-{i}", "LABEL": f"Inversor {i}", "RATING": "6 kW"}
        started = time.perf_counter()
        handle = acad.insert_block(com_drawing, BLOCK, [i * 25.0, 400], values)
        insert_ms.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        read = acad.read_attributes(com_drawing, handle)
        read_ms.append((time.perf_counter() - started) * 1000)
        assert read == values

    section = results.section("com")
    section["insert_block"] = summarize(insert_ms)
    section["read_attributes"] = summarize(read_ms)


def test_com_batch_200_inserts_200_lines(acad, com_drawing: str, results: Results) -> None:
    repeats = env_int("PVSLD_S2_BATCH_REPEATS", 5)
    samples = []
    for repeat in range(repeats):
        before = acad.modelspace_count(com_drawing)
        started = time.perf_counter()
        handles = acad.batch(
            com_drawing,
            BLOCK,
            inserts(200, row=-100.0 * repeat),
            lines(200, row=-100.0 * repeat),
            timeout=600,
        )
        samples.append((time.perf_counter() - started) * 1000)
        assert len(handles) == 200
        assert acad.modelspace_count(com_drawing) == before + 400

    results.section("com")["batch_200_200"] = summarize(samples)


def test_com_reliability_runs(acad, com_drawing: str, results: Results) -> None:
    """Baseline only: the same run shape as the plug-in's, with a 20 + 20 batch to bound time."""
    runs = env_int("PVSLD_S2_COM_RUNS", 100)
    failures: list[str] = []
    started = time.perf_counter()
    for run in range(runs):
        try:
            acad.ping()
            values = {"COMP_ID": f"R-{run}", "LABEL": "Interruptor", "RATING": "2x20 A"}
            handle = acad.insert_block(com_drawing, BLOCK, [run * 25.0, 2000], values)
            assert acad.read_attributes(com_drawing, handle) == values
            before = acad.modelspace_count(com_drawing)
            acad.batch(com_drawing, BLOCK, inserts(20, row=3000.0), lines(20, row=3000.0))
            assert acad.modelspace_count(com_drawing) == before + 40
        except Exception as exc:  # recorded, not raised: COM is the baseline
            failures.append(f"run {run}: {type(exc).__name__}: {exc}")

    results.section("com")["reliability"] = {
        "runs": runs,
        "failures": len(failures),
        "first_failures": failures[:5],
        "seconds": round(time.perf_counter() - started, 1),
        "run": "ping + insert + read-back + batch 20 inserts/20 lines + count check",
    }
