"""S2 plug-in latency and throughput (criteria: ping p95 < 50 ms; 200 + 200 batch < 2 s)."""

from __future__ import annotations

import time

import pytest
from s2_support import BLOCK, Results, env_int, inserts, lines, summarize, time_calls

pytestmark = pytest.mark.autocad

PING_P95_LIMIT_MS = 50.0
BATCH_LIMIT_MS = 2000.0


def test_plugin_loads_and_answers(bridge, plugin, results: Results) -> None:
    hello = bridge.server_info

    assert hello["protocol"] == 1
    assert bridge.ping()["pid"] == plugin.pid
    results.section("plugin_load")["hello"] = hello


def test_ping_p95_under_50_ms(bridge, results: Results) -> None:
    count = env_int("PVSLD_S2_PING_SAMPLES", 200)
    transport = summarize(time_calls(bridge.ping, count))
    main_thread = summarize(time_calls(lambda: bridge.ping(main_thread=True), count))

    section = results.section("plugin")
    section["ping_transport"] = transport
    section["ping_main_thread"] = main_thread
    assert transport["p95_ms"] < PING_P95_LIMIT_MS
    assert main_thread["p95_ms"] < PING_P95_LIMIT_MS


def test_insert_and_read_back(bridge, plugin_drawing: str, results: Results) -> None:
    count = env_int("PVSLD_S2_OP_SAMPLES", 50)
    bridge.insert_block(BLOCK, [0, 500], document=plugin_drawing)
    insert_ms, read_ms = [], []
    for i in range(count):
        values = {"COMP_ID": f"NET-{i}", "LABEL": f"Inversor {i}", "RATING": "6 kW"}
        started = time.perf_counter()
        handle = bridge.insert_block(BLOCK, [i * 25.0, 400], values, document=plugin_drawing)[
            "handle"
        ]
        insert_ms.append((time.perf_counter() - started) * 1000)
        started = time.perf_counter()
        read = bridge.read_attributes(handle=handle, document=plugin_drawing)
        read_ms.append((time.perf_counter() - started) * 1000)
        assert read[0]["attributes"] == values

    section = results.section("plugin")
    section["insert_block"] = summarize(insert_ms)
    section["read_attributes"] = summarize(read_ms)


def test_batch_200_inserts_200_lines_under_2_s(
    bridge, plugin_drawing: str, results: Results
) -> None:
    repeats = env_int("PVSLD_S2_BATCH_REPEATS", 5)
    wall, main_thread = [], []
    for repeat in range(repeats):
        before = bridge.drawing_stats(document=plugin_drawing)["modelspace_entities"]
        started = time.perf_counter()
        result = bridge.batch(
            BLOCK,
            inserts(200, row=-100.0 * repeat),
            lines(200, row=-100.0 * repeat),
            document=plugin_drawing,
        )
        wall.append((time.perf_counter() - started) * 1000)
        main_thread.append(result["main_thread_ms"])
        after = bridge.drawing_stats(document=plugin_drawing)["modelspace_entities"]
        assert (result["inserted"], result["lines"], after - before) == (200, 200, 400)
        sample = bridge.read_attributes(handle=result["handles"][123], document=plugin_drawing)
        assert sample[0]["attributes"]["COMP_ID"] == "PV-123"

    section = results.section("plugin")
    section["batch_200_200"] = summarize(wall)
    section["batch_200_200_main_thread"] = summarize(main_thread)
    assert max(wall) < BATCH_LIMIT_MS
