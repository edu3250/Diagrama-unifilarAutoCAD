"""Session fixtures for the S2 tests that drive a licensed AutoCAD 2027 (``--run-autocad``).

One AutoCAD instance per session, launched here through COM (never one that was already running)
with two scratch drawings: one for the COM baseline, one for the plug-in. The plug-in is loaded
with NETLOAD from the Release build; if AutoCAD shows its unsigned-DLL trust dialog, the session
waits for the owner to answer it (``PVSLD_S2_LOAD_WAIT`` seconds) and never answers it itself.

Teardown never force-kills AutoCAD: it closes our drawings without saving and calls ``Quit()``;
if AutoCAD does not exit, it is left running and the results file says so.

Environment knobs: ``PVSLD_S2_RESULTS`` (JSON path, default ``build/s2/results.json``),
``PVSLD_S2_LOAD_WAIT`` (180), ``PVSLD_S2_PING_SAMPLES`` (200), ``PVSLD_S2_OP_SAMPLES`` (50),
``PVSLD_S2_BATCH_REPEATS`` (5), ``PVSLD_S2_RUNS`` (100), ``PVSLD_S2_COM_RUNS`` (100).
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from s2_support import PLUGIN_DLL, REPO_ROOT, Results, env_float

if sys.platform == "win32":
    from pvsld.transports.com import AutoCADCom, acad_pids, describe_dialogs, visible_dialogs
    from pvsld.transports.pipe import BridgeEndpoint, PipeClient, discover_endpoint
    from pvsld.transports.protocol import BridgeConnectionError

TRUST_DIALOG_WORDS = ("seguridad", "security", "ejecutable", "executable")


@pytest.fixture(scope="session")
def results() -> Iterator[Results]:
    path = Path(os.environ.get("PVSLD_S2_RESULTS", REPO_ROOT / "build/s2/results.json"))
    collected = Results(path)
    yield collected
    collected.save()


@pytest.fixture(scope="session")
def acad(results: Results) -> Iterator[AutoCADCom]:
    session = results.section("autocad")
    preexisting = sorted(acad_pids())
    session["preexisting_acad_pids"] = preexisting  # never touched
    try:
        client = AutoCADCom.launch(startup_timeout=env_float("PVSLD_S2_STARTUP_TIMEOUT", 240))
    except Exception as exc:
        session["launch_error"] = str(exc)
        pytest.fail(f"AutoCAD could not be started: {exc}")
    session.update(
        pid=client.pid,
        startup_s=round(client.startup_seconds, 1),
        version=client.ping(),
        com_binding=client.binding,
    )
    yield client
    started = time.monotonic()
    exited = client.quit(timeout=120)
    note = "closed our drawings without saving, then Quit()"
    if not exited:
        dialogs = describe_dialogs(client.pid)
        note = f"AutoCAD pid {client.pid} did not exit and was LEFT RUNNING ({dialogs})"
    session["shutdown"] = {
        "exited": exited,
        "seconds": round(time.monotonic() - started, 1),
        "note": note,
    }


@pytest.fixture(scope="session")
def com_drawing(acad: AutoCADCom) -> str:
    return acad.new_drawing()


@pytest.fixture(scope="session")
def plugin_drawing(acad: AutoCADCom, com_drawing: str) -> str:
    return acad.new_drawing()  # created last, so it is the active drawing for PostCommand


@pytest.fixture(scope="session")
def plugin(acad: AutoCADCom, plugin_drawing: str, results: Results) -> BridgeEndpoint:
    """NETLOAD the plug-in into our AutoCAD and wait for its discovery file."""
    section = results.section("plugin_load")
    if not PLUGIN_DLL.exists():
        section["error"] = "plug-in not built"
        pytest.skip(
            "build the plug-in first: dotnet build plugin/PvSld.AutoCAD.slnx -c Release "
            f"({PLUGIN_DLL})"
        )
    wait = env_float("PVSLD_S2_LOAD_WAIT", 180)
    path = str(PLUGIN_DLL).replace("\\", "/")
    started = time.monotonic()
    acad.post_command(plugin_drawing, f'(command "_.NETLOAD" "{path}") ')  # space = Enter

    endpoint: BridgeEndpoint | None = None
    trust_dialogs: list[str] = []
    deadline = started + wait
    while time.monotonic() < deadline:
        try:
            endpoint = discover_endpoint(pid=acad.pid)
            break
        except BridgeConnectionError:
            pass
        for dialog in visible_dialogs(acad.pid):
            text = " ".join((dialog.title, *dialog.texts)).lower()
            if (
                any(word in text for word in TRUST_DIALOG_WORDS)
                and dialog.title not in trust_dialogs
            ):
                trust_dialogs.append(dialog.title)
                print(  # shown with -s, so the owner knows what to do
                    f"\n[S2] AutoCAD shows '{dialog.title}': the owner must choose "
                    f"'Cargar una vez' (Load once) to continue; waiting up to {wait:.0f} s.",
                    flush=True,
                )
        time.sleep(0.5)

    section.update(
        dll=str(PLUGIN_DLL),
        trust_dialogs=trust_dialogs,
        seconds=round(time.monotonic() - started, 1),
        loaded=endpoint is not None,
    )
    if endpoint is None:
        section["error"] = (
            f"no discovery file after {wait:.0f} s; dialogs now: {describe_dialogs(acad.pid)}"
        )
        pytest.skip(f"plug-in not loaded: {section['error']}")
    section.update(pipe=endpoint.pipe, server=endpoint.server, discovery_file=str(endpoint.path))
    return endpoint


@pytest.fixture(scope="session")
def bridge(plugin: BridgeEndpoint) -> Iterator[PipeClient]:
    client = PipeClient.for_endpoint(plugin, timeout=60)
    client.connect()
    yield client
    client.close()
