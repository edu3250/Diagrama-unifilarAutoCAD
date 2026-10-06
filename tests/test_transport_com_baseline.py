"""COM baseline logic without AutoCAD: retry policy, STA worker and operations on a fake model."""

# The fakes mirror AutoCAD's COM member names (InsertBlock, GetAttributes, ...).
# ruff: noqa: N802

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

from pvsld.transports import com
from pvsld.transports.com import (
    RPC_E_CALL_REJECTED,
    RPC_E_SERVERCALL_RETRYLATER,
    AutoCADCom,
    ComBusyError,
    ComError,
    ComStartupError,
    ComTimeoutError,
    RetryingProxy,
    RetryPolicy,
    StaWorker,
    call_with_retry,
    is_rejected,
)


class FakeComError(Exception):
    """Shaped like pywintypes.com_error: hresult plus excepinfo."""

    def __init__(self, hresult: int, scode: int | None = None) -> None:
        super().__init__(hresult)
        self.hresult = hresult
        self.excepinfo = (0, "AutoCAD", "busy", None, 0, scode) if scode is not None else None


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


def _flaky(failures: int, error: Exception, value: str = "ok") -> Any:
    calls = {"n": 0}

    def fn() -> str:
        calls["n"] += 1
        if calls["n"] <= failures:
            raise error
        return value

    fn.calls = calls  # type: ignore[attr-defined]
    return fn


# -- retry policy -----------------------------------------------------------------------------


def test_is_rejected_reads_hresult_and_inner_scode() -> None:
    assert is_rejected(FakeComError(RPC_E_CALL_REJECTED))
    assert is_rejected(FakeComError(RPC_E_SERVERCALL_RETRYLATER))
    assert is_rejected(FakeComError(-2147352567, scode=RPC_E_CALL_REJECTED))  # DISP_E_EXCEPTION
    assert not is_rejected(FakeComError(-2147352567, scode=-1))
    assert not is_rejected(ValueError("x"))


def test_retry_reissues_rejected_calls_with_backoff() -> None:
    clock = Clock()
    fn = _flaky(3, FakeComError(RPC_E_CALL_REJECTED))

    result = call_with_retry(fn, RetryPolicy(budget=5), sleep=clock.sleep, clock=clock.time)

    assert result == "ok"
    assert fn.calls["n"] == 4
    assert clock.sleeps == [0.02, 0.04, 0.08]


def test_retry_does_not_retry_other_errors() -> None:
    fn = _flaky(1, KeyError("missing block"))

    with pytest.raises(KeyError):
        call_with_retry(fn, RetryPolicy(), sleep=lambda _: None)
    assert fn.calls["n"] == 1


def test_retry_gives_up_with_an_actionable_busy_error() -> None:
    clock = Clock()
    fn = _flaky(10_000, FakeComError(RPC_E_CALL_REJECTED))

    with pytest.raises(ComBusyError, match="Finish or cancel") as caught:
        call_with_retry(fn, RetryPolicy(budget=2.0), sleep=clock.sleep, clock=clock.time)

    assert clock.now <= 2.0
    assert isinstance(caught.value.__cause__, FakeComError)


def test_policy_delays_are_capped() -> None:
    delays = RetryPolicy(initial_delay=0.1, max_delay=0.3).delays()

    assert [next(delays) for _ in range(4)] == [0.1, 0.2, 0.3, 0.3]


# -- per-call retry proxy ---------------------------------------------------------------------


class Node:
    """A COM-looking object: has ``_oleobj_`` and rejects the first access of each member."""

    def __init__(self, name: str) -> None:
        self._oleobj_ = object()
        self.name = name
        self._rejections: dict[str, int] = {}
        self.text = ""
        self.received: tuple[Any, ...] = ()

    def _maybe_reject(self, member: str) -> None:
        if self._rejections.get(member, 0) == 0:
            self._rejections[member] = 1
            raise FakeComError(RPC_E_CALL_REJECTED)

    def __getattribute__(self, member: str) -> Any:
        if member in ("child", "children", "describe"):
            object.__getattribute__(self, "_maybe_reject")(member)
        return object.__getattribute__(self, member)

    @property
    def child(self) -> Node:
        return Node(self.name + ".child")

    def children(self) -> tuple[Node, ...]:
        return (Node("a"), Node("b"))

    def describe(self, *args: Any) -> str:
        self.received = args
        return f"{self.name}{args}"


def test_proxy_retries_every_property_and_method_and_wraps_results() -> None:
    proxy = RetryingProxy(Node("root"), RetryPolicy(initial_delay=0.0))

    child = proxy.child
    kids = proxy.children()
    described = proxy.describe(child, 1)
    proxy.text = "hola"

    assert isinstance(child, RetryingProxy)
    assert all(isinstance(kid, RetryingProxy) for kid in kids)
    assert described.startswith("root(")
    assert proxy.wrapped.received[0] is child.wrapped  # proxies are unwrapped on the way in
    assert proxy.text == "hola"
    assert "RetryingProxy" in repr(proxy)


# -- STA worker -------------------------------------------------------------------------------


@pytest.fixture
def worker() -> Iterator[StaWorker]:
    pumped = threading.Event()
    sta = StaWorker(initialize=None, uninitialize=None, pump=pumped.set, idle_interval=0.01)
    sta.pumped = pumped  # type: ignore[attr-defined]
    yield sta
    sta.close()


def test_worker_runs_everything_on_one_thread(worker: StaWorker) -> None:
    ids = {worker.call(threading.get_ident, timeout=5) for _ in range(5)}

    assert ids == {worker.thread_id}
    assert worker.thread_id != threading.get_ident()


def test_worker_pumps_messages_while_idle(worker: StaWorker) -> None:
    assert worker.pumped.wait(2)  # type: ignore[attr-defined]


def test_worker_propagates_exceptions(worker: StaWorker) -> None:
    def boom() -> None:
        raise ValueError("inside AutoCAD")

    with pytest.raises(ValueError, match="inside AutoCAD"):
        worker.call(boom, timeout=5)


def test_worker_call_times_out_when_the_thread_is_blocked(worker: StaWorker) -> None:
    release = threading.Event()
    worker.submit(release.wait, 5)

    with pytest.raises(ComTimeoutError, match="dialog"):
        worker.call(lambda: 1, timeout=0.1)

    release.set()
    assert worker.call(lambda: 2, timeout=5) == 2


def test_worker_reports_failed_com_initialisation() -> None:
    def fail() -> None:
        raise OSError("CoInitializeEx failed")

    with pytest.raises(ComError, match="initialisation failed"):
        StaWorker(initialize=fail, uninitialize=None, pump=None)


def test_closed_worker_refuses_work() -> None:
    sta = StaWorker(initialize=None, uninitialize=None, pump=None)
    sta.close()

    with pytest.raises(ComError, match="stopped"):
        sta.submit(lambda: None)


# -- AutoCADCom operations on a fake object model ----------------------------------------------


class FakeAttribute:
    def __init__(self, tag: str) -> None:
        self._oleobj_ = object()
        self.TagString = tag
        self.TextString = ""


class FakeReference:
    def __init__(self, handle: str, tags: tuple[str, ...]) -> None:
        self._oleobj_ = object()
        self.Handle = handle
        self._attributes = tuple(FakeAttribute(tag) for tag in tags)

    def GetAttributes(self) -> tuple[FakeAttribute, ...]:
        return self._attributes


class FakeDefinition:
    def __init__(self) -> None:
        self._oleobj_ = object()
        self.tags: list[str] = []
        self.Closed = False

    def AddLightWeightPolyline(self, points: Any) -> FakeDefinition:
        return self

    def AddCircle(self, center: Any, radius: float) -> None:
        pass

    def AddAttribute(
        self, height: float, mode: int, prompt: str, point: Any, tag: str, value: str
    ) -> None:
        self.tags.append(tag)


class FakeBlocks:
    def __init__(self) -> None:
        self._oleobj_ = object()
        self.definitions: dict[str, FakeDefinition] = {}

    def Item(self, name: str) -> FakeDefinition:
        if name not in self.definitions:
            raise FakeComError(-2145386476)  # "key not found", not a rejection
        return self.definitions[name]

    def Add(self, origin: Any, name: str) -> FakeDefinition:
        self.definitions[name] = FakeDefinition()
        return self.definitions[name]


class FakeModelSpace:
    def __init__(self, document: FakeDocument) -> None:
        self._oleobj_ = object()
        self._document = document
        self.entities: dict[str, Any] = {}

    @property
    def Count(self) -> int:
        return len(self.entities)

    def InsertBlock(self, point: Any, name: str, *scale_and_rotation: float) -> FakeReference:
        handle = self._document.next_handle()
        tags = tuple(self._document.Blocks.definitions[name].tags)
        self.entities[handle] = FakeReference(handle, tags)
        return self.entities[handle]

    def AddLine(self, start: Any, end: Any) -> None:
        self.entities[self._document.next_handle()] = ("line", start, end)


class FakeDocument:
    def __init__(self, name: str) -> None:
        self._oleobj_ = object()
        self.Name = name
        self.Blocks = FakeBlocks()
        self.ModelSpace = FakeModelSpace(self)
        self.closed_with: bool | None = None
        self.posted: list[str] = []
        self._handle = 0x100

    def next_handle(self) -> str:
        self._handle += 1
        return format(self._handle, "X")

    def HandleToObject(self, handle: str) -> Any:
        return self.ModelSpace.entities[handle]

    def PostCommand(self, text: str) -> None:
        self.posted.append(text)

    def GetVariable(self, name: str) -> Any:
        return {"CMDACTIVE": 0}[name]

    def Close(self, save: bool) -> None:
        self.closed_with = save


class FakeDocuments:
    def __init__(self) -> None:
        self._oleobj_ = object()
        self.items: list[FakeDocument] = [FakeDocument("Dibujo1.dwg")]

    @property
    def Count(self) -> int:
        return len(self.items)

    def Item(self, index: int) -> FakeDocument:
        return self.items[index]

    def Add(self) -> FakeDocument:
        self.items.append(FakeDocument(f"Dibujo{len(self.items) + 1}.dwg"))
        return self.items[-1]


class FakeAcadState:
    _oleobj_ = object()
    IsQuiescent = True


class FakeApplication:
    def __init__(self) -> None:
        self._oleobj_ = object()
        self.Version = "26.0s (LMS Tech)"
        self.Documents = FakeDocuments()
        self.quit_called = False

    def GetAcadState(self) -> FakeAcadState:
        return FakeAcadState()

    def Quit(self) -> None:
        self.quit_called = True


@pytest.fixture
def acad(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[AutoCADCom, FakeApplication]]:
    monkeypatch.setattr(com, "_point", lambda x, y, z=0.0: (x, y, z))
    monkeypatch.setattr(com, "_doubles", tuple)
    app = FakeApplication()
    sta = StaWorker(initialize=None, uninitialize=None, pump=None)
    client = AutoCADCom(
        sta, RetryingProxy(app, RetryPolicy()), pid=0, retry=RetryPolicy(), call_timeout=5
    )
    yield client, app
    sta.close()


def test_com_insert_read_and_batch_on_the_fake_model(
    acad: tuple[AutoCADCom, FakeApplication],
) -> None:
    client, app = acad
    name = client.new_drawing()

    handle = client.insert_block(
        name, "PVSLD_S2_TEST", [0, 0], {"comp_id": "PV-1", "LABEL": "Módulo"}
    )
    handles = client.batch(
        name,
        "PVSLD_S2_TEST",
        [{"position": [i, 0], "attributes": {"RATING": "550 W"}} for i in range(5)],
        [{"start": [0, 0], "end": [1, 1]}] * 5,
    )

    assert client.read_attributes(name, handle) == {
        "COMP_ID": "PV-1",
        "LABEL": "Módulo",
        "RATING": "",
    }
    assert client.read_attributes(name, handles[0])["RATING"] == "550 W"
    assert client.modelspace_count(name) == 11
    assert app.Documents.items[1].Blocks.definitions["PVSLD_S2_TEST"].tags == [
        "COMP_ID",
        "LABEL",
        "RATING",
    ]
    assert client.ping().startswith("26.0")
    assert client.document_names() == ["Dibujo1.dwg", "Dibujo2.dwg"]


def test_com_post_command_variables_and_close(acad: tuple[AutoCADCom, FakeApplication]) -> None:
    client, app = acad
    name = client.new_drawing()

    client.post_command(name, "_.LINE ")
    assert client.get_variable(name, "CMDACTIVE") == 0
    assert client.is_quiescent()
    client.close_drawing(name)

    assert app.Documents.items[1].posted == ["_.LINE "]
    assert app.Documents.items[1].closed_with is False
    with pytest.raises(ComError, match="no open drawing"):
        client.get_variable("Nope.dwg", "CMDACTIVE")


def test_com_quit_closes_every_drawing_without_saving(
    acad: tuple[AutoCADCom, FakeApplication],
) -> None:
    client, app = acad
    client.new_drawing()

    exited = client.quit(timeout=1)

    assert exited  # pid 0 is never alive
    assert app.quit_called
    assert all(document.closed_with is False for document in app.Documents.items)


def test_launch_guards_run_before_anything_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    started = []
    monkeypatch.setattr(com, "acad_pids", lambda: started.append(1) or set())

    if sys.platform != "win32":
        with pytest.raises(ComStartupError, match="Windows"):
            AutoCADCom.launch()
    else:
        with pytest.raises(ValueError, match="180"):
            AutoCADCom.launch(startup_timeout=10)
    assert started == []


def test_startup_failure_windows_are_detected_in_any_window_class(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = [
        com.WindowInfo(1, "AfxMDIFrame140u", "Autodesk AutoCAD 2027", ()),
        com.WindowInfo(
            2,
            "WindowsForms10.Window.8.app.0.1",
            "AutoCAD",
            ("Excepción no controlada en un componente de la aplicación", "Bad IL format."),
        ),
    ]
    monkeypatch.setattr(com, "process_windows", lambda pid: windows)

    assert [w.hwnd for w in com.startup_failures(42)] == [2]
    with pytest.raises(com.StartupBlockedError, match="Bad IL format") as caught:
        com._raise_if_startup_failed(42)
    assert caught.value.pid == 42


def test_hresult_of_plain_exception_is_none() -> None:
    assert com.hresult_of(ValueError()) is None
    assert time.monotonic() > 0  # keeps the clock import honest for the Clock double
