"""S2 busy handling: a modal dialog, a running command and a command waiting for input.

Criterion: the plug-in answers an actionable "busy" error within 5 s and AutoCAD never hangs.
Each scenario also checks that the refused request does not run later, and records how the COM
baseline behaves in the same situation. Only dialogs and commands this test created are touched.
"""

from __future__ import annotations

import time
from typing import Any

import pytest
from s2_support import BLOCK, Results, click_default_button, press_escape, wait_until

pytestmark = pytest.mark.autocad

BUSY_LIMIT_S = 5.0
ALERT_TEXT = "pvsld S2 busy test"


def _try_plugin_insert(bridge: Any, drawing: str) -> dict[str, Any]:
    from pvsld.transports.protocol import BridgeBusyError

    started = time.perf_counter()
    try:
        bridge.insert_block(
            BLOCK, [0, -9000], {"COMP_ID": "MUST-NOT-EXIST"}, document=drawing, timeout=30
        )
        outcome: dict[str, Any] = {"outcome": "executed"}
    except BridgeBusyError as exc:
        outcome = {"outcome": "busy", "reason": exc.reason, "message": exc.message}
    outcome["seconds"] = round(time.perf_counter() - started, 3)
    return outcome


def _try_com(acad: Any, drawing: str) -> dict[str, Any]:
    from pvsld.transports.com import ComError

    started = time.perf_counter()
    try:
        acad.modelspace_count(drawing)
        outcome = {"outcome": "answered"}
    except ComError as exc:
        outcome = {"outcome": type(exc).__name__, "message": str(exc)[:160]}
    outcome["seconds"] = round(time.perf_counter() - started, 3)
    return outcome


def _idle(bridge: Any, drawing: str) -> bool:
    from pvsld.transports.protocol import BridgeBusyError

    try:
        bridge.drawing_stats(document=drawing, timeout=10)
        return True
    except BridgeBusyError:
        return False


def _assert_busy_and_recovered(
    record: dict[str, Any], before: dict, bridge: Any, drawing: str
) -> None:
    plugin = record["plugin"]
    assert plugin["outcome"] == "busy", record
    assert plugin["seconds"] <= BUSY_LIMIT_S, record
    assert record["recovered"], record
    # The refused insert was dropped, not queued: nothing appeared once AutoCAD became idle.
    assert bridge.drawing_stats(document=drawing) == before
    assert not [
        r
        for r in bridge.read_attributes(block=BLOCK, document=drawing)
        if r["attributes"].get("COMP_ID") == "MUST-NOT-EXIST"
    ]


def test_busy_while_a_modal_dialog_is_open(
    acad, bridge, plugin_drawing: str, com_drawing: str, results: Results
) -> None:
    from pvsld.transports.com import visible_dialogs

    before = bridge.drawing_stats(document=plugin_drawing)
    acad.post_command(plugin_drawing, f'(alert "{ALERT_TEXT}") ')
    record: dict[str, Any] = {}
    dialog = None
    try:
        assert wait_until(
            lambda: any(ALERT_TEXT in " ".join(d.texts) for d in visible_dialogs(acad.pid)), 15
        ), "the test alert did not appear"
        dialog = next(d for d in visible_dialogs(acad.pid) if ALERT_TEXT in " ".join(d.texts))
        record["plugin"] = _try_plugin_insert(bridge, plugin_drawing)
        record["com"] = _try_com(acad, com_drawing)
    finally:
        if dialog is not None:
            click_default_button(dialog.hwnd)  # our own alert, in our own AutoCAD
    started = time.perf_counter()
    record["recovered"] = wait_until(lambda: _idle(bridge, plugin_drawing), 30)
    record["recovery_s"] = round(time.perf_counter() - started, 2)
    results.section("busy")["modal_dialog"] = record

    _assert_busy_and_recovered(record, before, bridge, plugin_drawing)


def test_busy_while_a_command_is_running(
    acad, bridge, plugin_drawing: str, com_drawing: str, results: Results
) -> None:
    """DELAY keeps a command (and LISP) running for 6 s, then finishes on its own."""
    before = bridge.drawing_stats(document=plugin_drawing)
    acad.post_command(plugin_drawing, '(command "_.DELAY" 6000) ')
    time.sleep(0.5)
    record: dict[str, Any] = {"plugin": _try_plugin_insert(bridge, plugin_drawing)}
    record["com"] = _try_com(acad, com_drawing)
    started = time.perf_counter()
    record["recovered"] = wait_until(lambda: _idle(bridge, plugin_drawing), 30)
    record["recovery_s"] = round(time.perf_counter() - started, 2)
    results.section("busy")["command_running"] = record

    _assert_busy_and_recovered(record, before, bridge, plugin_drawing)


def test_busy_while_a_command_waits_for_input(
    acad, bridge, plugin_drawing: str, com_drawing: str, results: Results
) -> None:
    """LINE waits for a point; the test cancels it afterwards with Esc."""
    from pvsld.transports.com import ComError

    before = bridge.drawing_stats(document=plugin_drawing)
    acad.post_command(plugin_drawing, "_.LINE ")
    time.sleep(1.0)
    record: dict[str, Any] = {"plugin": _try_plugin_insert(bridge, plugin_drawing)}
    record["com"] = _try_com(acad, com_drawing)
    cancel_attempts = []
    for keys in ("\x1b", "\x1b\x1b", "\x03"):
        try:
            acad.post_command(plugin_drawing, keys)
            cancel_attempts.append({"keys": repr(keys), "sent": True})
        except ComError as exc:
            cancel_attempts.append({"keys": repr(keys), "sent": False, "error": str(exc)[:120]})
        if wait_until(lambda: _idle(bridge, plugin_drawing), 5):
            break
    else:
        cancel_attempts.append(
            {"keys": "Esc keystroke to our AutoCAD", "sent": press_escape(acad.pid)}
        )
    started = time.perf_counter()
    record["cancel"] = cancel_attempts
    record["recovered"] = wait_until(lambda: _idle(bridge, plugin_drawing), 15)
    if not record["recovered"]:
        # The owner attends the run: ask for Esc rather than leave AutoCAD inside LINE.
        print(
            "\n[S2] Please press Esc in the AutoCAD window to cancel the test's LINE.", flush=True
        )
        record["recovered"] = wait_until(lambda: _idle(bridge, plugin_drawing), 120)
        record["cancel"].append({"keys": "Esc by the owner (prompted)", "sent": True})
    record["recovery_s"] = round(time.perf_counter() - started, 2)
    results.section("busy")["command_waiting_for_input"] = record

    _assert_busy_and_recovered(record, before, bridge, plugin_drawing)


def test_autocad_is_healthy_after_the_busy_scenarios(
    acad, bridge, plugin_drawing: str, results: Results
) -> None:
    healthy = {
        "quiescent": acad.is_quiescent(),
        "com_ping": acad.ping(),
        "plugin_main_thread_ping": bridge.ping(main_thread=True)["pong"],
        "plugin_insert": bool(
            bridge.insert_block(BLOCK, [0, -9500], {"COMP_ID": "AFTER"}, document=plugin_drawing)[
                "handle"
            ]
        ),
    }
    results.section("busy")["after"] = healthy

    assert healthy["quiescent"]
    assert healthy["plugin_main_thread_ping"] is True
    assert healthy["plugin_insert"]
