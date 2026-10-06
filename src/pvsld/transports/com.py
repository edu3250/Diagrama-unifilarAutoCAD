"""Throwaway COM baseline for spike S2 (ADR-0001 option O3): measurement only, never product code.

It drives an AutoCAD 2027 instance that *this process launched*, through pywin32 on one dedicated
single-threaded-apartment (STA) thread, the way a careful Python MCP server would have to.

Busy handling: AutoCAD rejects COM calls while it is busy (``RPC_E_CALL_REJECTED`` or
``RPC_E_SERVERCALL_RETRYLATER``). The usual fix is an ``IMessageFilter`` whose
``RetryRejectedCall`` asks COM to re-issue the call; pywin32 312 cannot register one, so
:func:`call_with_retry` applies the same policy per call (a rejected call was never executed, so
re-issuing it is safe), and :class:`RetryingProxy` wraps every COM object so that *each* property
access and method call gets that policy.

Safety rules (spike S2 brief, and lessons from a truncated AutoCAD cache file):

* Never force-kill AutoCAD. :meth:`AutoCADCom.quit` closes this process's drawings without saving
  and calls ``Quit()``; if AutoCAD does not exit, it is left running and reported.
* After launching, wait until ``GetAcadState().IsQuiescent`` (budget >= 180 s), treating rejected
  calls and the ``AttributeError`` pywin32 raises for a rejected name lookup as "still starting".
* Never start a second instance while one may still be starting, and never drive an AutoCAD that
  was already running.
"""

from __future__ import annotations

import concurrent.futures
import contextlib
import queue
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PROG_ID = "AutoCAD.Application.26"  # AutoCAD 2027

RPC_E_CALL_REJECTED = -2147418111  # 0x80010001
RPC_E_SERVERCALL_RETRYLATER = -2147417846  # 0x8001010A
RETRYABLE_HRESULTS = frozenset({RPC_E_CALL_REJECTED, RPC_E_SERVERCALL_RETRYLATER})

AC_ATTRIBUTE_MODE_NORMAL = 0
AC_ATTRIBUTE_MODE_INVISIBLE = 1


class ComError(Exception):
    """Base class of the COM baseline's errors."""


class ComBusyError(ComError):
    """AutoCAD kept rejecting a call until the retry budget ran out."""


class ComTimeoutError(ComError):
    """A call did not return in time; the STA thread may be blocked inside AutoCAD."""


class ComStartupError(ComError):
    """AutoCAD could not be started, or did not become ready in time."""


def hresult_of(exc: BaseException) -> int | None:
    """The HRESULT carried by a pywin32 ``com_error`` (or its inner SCODE), if any."""
    hresult = getattr(exc, "hresult", None)
    if hresult in RETRYABLE_HRESULTS:
        return hresult
    excepinfo = getattr(exc, "excepinfo", None)
    if isinstance(excepinfo, tuple) and len(excepinfo) > 5 and excepinfo[5] in RETRYABLE_HRESULTS:
        return excepinfo[5]
    return hresult if isinstance(hresult, int) else None


def is_rejected(exc: BaseException) -> bool:
    """Whether AutoCAD refused the call because it was busy (so it was not executed)."""
    return hresult_of(exc) in RETRYABLE_HRESULTS


@dataclass(frozen=True)
class RetryPolicy:
    """How long to keep re-issuing rejected calls, with exponential back-off."""

    budget: float = 5.0
    initial_delay: float = 0.02
    max_delay: float = 0.5

    def delays(self) -> Iterator[float]:
        delay = self.initial_delay
        while True:
            yield delay
            delay = min(delay * 2, self.max_delay)


def call_with_retry(
    fn: Callable[[], Any],
    policy: RetryPolicy,
    *,
    retryable: Callable[[BaseException], bool] = is_rejected,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> Any:
    """Call ``fn``; while it fails with a retryable error, wait and call again within the budget."""
    start = clock()
    for attempts, delay in enumerate(policy.delays(), start=1):
        try:
            return fn()
        except Exception as exc:
            if not retryable(exc):
                raise
            elapsed = clock() - start
            if elapsed + delay > policy.budget:
                raise ComBusyError(
                    f"AutoCAD rejected the call for {elapsed:.1f} s ({attempts} attempts): it is "
                    "busy (modal dialog, active command or script). Finish or cancel it in "
                    "AutoCAD, then retry."
                ) from exc
            sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover


class RetryingProxy:
    """Wraps a COM object so every attribute read, write and method call uses the retry policy."""

    __slots__ = ("_obj", "_policy")

    def __init__(self, obj: Any, policy: RetryPolicy) -> None:
        object.__setattr__(self, "_obj", obj)
        object.__setattr__(self, "_policy", policy)

    @property
    def wrapped(self) -> Any:
        return self._obj

    def __getattr__(self, name: str) -> Any:
        value = call_with_retry(lambda: getattr(self._obj, name), self._policy)
        if callable(value) and not _is_com_object(value):
            return _RetryingCallable(value, self._policy)
        return _wrap(value, self._policy)

    def __setattr__(self, name: str, value: Any) -> None:
        call_with_retry(lambda: setattr(self._obj, name, _unwrap(value)), self._policy)

    def __repr__(self) -> str:
        return f"RetryingProxy({self._obj!r})"


class _RetryingCallable:
    __slots__ = ("_fn", "_policy")

    def __init__(self, fn: Callable[..., Any], policy: RetryPolicy) -> None:
        self._fn = fn
        self._policy = policy

    def __call__(self, *args: Any) -> Any:
        plain = tuple(_unwrap(arg) for arg in args)
        return _wrap(call_with_retry(lambda: self._fn(*plain), self._policy), self._policy)


def _is_com_object(value: Any) -> bool:
    return hasattr(value, "_oleobj_")


def _wrap(value: Any, policy: RetryPolicy) -> Any:
    if _is_com_object(value):
        return RetryingProxy(value, policy)
    if isinstance(value, tuple):
        return tuple(_wrap(item, policy) for item in value)
    return value


def _unwrap(value: Any) -> Any:
    return value.wrapped if isinstance(value, RetryingProxy) else value


def _co_initialize() -> None:
    import pythoncom

    pythoncom.CoInitializeEx(pythoncom.COINIT_APARTMENTTHREADED)


def _co_uninitialize() -> None:
    import pythoncom

    pythoncom.CoUninitialize()


def _pump_messages() -> None:
    import pythoncom

    pythoncom.PumpWaitingMessages()


class StaWorker:
    """One long-lived thread that owns every COM object (a single-threaded apartment).

    MCP's Python SDK runs sync tools on pool threads; COM objects must not cross apartments, so
    all COM work is funnelled through this queue. While idle the thread pumps window messages, as
    an STA thread should.
    """

    def __init__(
        self,
        name: str = "pvsld-com-sta",
        *,
        initialize: Callable[[], None] | None = _co_initialize,
        uninitialize: Callable[[], None] | None = _co_uninitialize,
        pump: Callable[[], None] | None = _pump_messages,
        idle_interval: float = 0.05,
    ) -> None:
        self._queue: queue.Queue[Any] = queue.Queue()
        self._initialize = initialize
        self._uninitialize = uninitialize
        self._pump = pump
        self._idle_interval = idle_interval
        self._ready = threading.Event()
        self._startup_error: BaseException | None = None
        self._thread = threading.Thread(target=self._run, name=name, daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._startup_error is not None:
            raise ComError(f"COM initialisation failed: {self._startup_error}")

    @property
    def thread_id(self) -> int | None:
        return self._thread.ident

    def submit(self, fn: Callable[..., Any], *args: Any) -> concurrent.futures.Future[Any]:
        if not self._thread.is_alive():
            raise ComError("the STA worker has stopped")
        future: concurrent.futures.Future[Any] = concurrent.futures.Future()
        self._queue.put((future, fn, args))
        return future

    def call(self, fn: Callable[..., Any], *args: Any, timeout: float) -> Any:
        future = self.submit(fn, *args)
        try:
            return future.result(timeout=timeout)
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise ComTimeoutError(
                f"no answer from AutoCAD within {timeout:.0f} s; it may be showing a dialog or "
                "running a long command"
            ) from exc

    def close(self, timeout: float = 10.0) -> None:
        if self._thread.is_alive():
            self._queue.put(None)
            self._thread.join(timeout)

    def _run(self) -> None:
        try:
            if self._initialize:
                self._initialize()
        except BaseException as exc:
            self._startup_error = exc
            self._ready.set()
            return
        self._ready.set()
        try:
            while True:
                try:
                    item = self._queue.get(timeout=self._idle_interval)
                except queue.Empty:
                    if self._pump:
                        self._pump()
                    continue
                if item is None:
                    break
                future, fn, args = item
                if not future.set_running_or_notify_cancel():
                    continue
                try:
                    future.set_result(fn(*args))
                except BaseException as exc:
                    future.set_exception(exc)
        finally:
            if self._uninitialize:
                self._uninitialize()


# -- processes and windows (Windows only) --------------------------------------------------------


def acad_pids() -> set[int]:
    """Ids of every running ``acad.exe`` (any user session visible to this one)."""
    output = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq acad.exe", "/FO", "CSV", "/NH"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout
    pids = set()
    for row in output.splitlines():
        fields = [f.strip('"') for f in row.split('","')]
        if len(fields) > 1 and fields[0].lower() == "acad.exe" and fields[1].isdigit():
            pids.add(int(fields[1]))
    return pids


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    class_name: str
    title: str
    texts: tuple[str, ...]


def process_windows(pid: int) -> list[WindowInfo]:
    """Visible top-level windows of ``pid`` with the texts of their child controls."""
    import pywintypes
    import win32gui
    import win32process

    found: list[WindowInfo] = []

    def visit(hwnd: int, _: Any) -> bool:
        if win32gui.IsWindowVisible(hwnd) and win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
            texts: list[str] = []

            def child(handle: int, __: Any) -> bool:
                text = win32gui.GetWindowText(handle)
                if text:
                    texts.append(text)
                return True

            with contextlib.suppress(pywintypes.error):
                win32gui.EnumChildWindows(hwnd, child, None)
            found.append(
                WindowInfo(
                    hwnd, win32gui.GetClassName(hwnd), win32gui.GetWindowText(hwnd), tuple(texts)
                )
            )
        return True

    win32gui.EnumWindows(visit, None)
    return found


def visible_dialogs(pid: int) -> list[WindowInfo]:
    """Standard dialog boxes (``#32770``) currently shown by ``pid``."""
    return [w for w in process_windows(pid) if w.class_name == "#32770"]


def describe_dialogs(pid: int) -> str:
    dialogs = visible_dialogs(pid)
    if not dialogs:
        return "no dialog is visible"
    return "; ".join(f"{d.title!r} {list(d.texts)[:6]}" for d in dialogs)


# -- the AutoCAD session --------------------------------------------------------------------------


def _point(x: float, y: float, z: float = 0.0) -> Any:
    import pythoncom
    import win32com.client

    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, (x, y, z))


def _doubles(values: Sequence[float]) -> Any:
    import pythoncom
    import win32com.client

    return win32com.client.VARIANT(pythoncom.VT_ARRAY | pythoncom.VT_R8, tuple(values))


def _starting(exc: BaseException) -> bool:
    """During start-up pywin32 also reports a rejected name lookup as a bare AttributeError."""
    return is_rejected(exc) or isinstance(exc, AttributeError)


class AutoCADCom:
    """Drives one AutoCAD instance this process launched, from a dedicated STA thread."""

    def __init__(
        self,
        worker: StaWorker,
        app: RetryingProxy,
        pid: int,
        *,
        retry: RetryPolicy,
        call_timeout: float,
        startup_seconds: float = 0.0,
        binding: str = "",
    ) -> None:
        self._worker = worker
        self._app = app
        self.pid = pid
        self.retry = retry
        self.call_timeout = call_timeout
        self.startup_seconds = startup_seconds
        self.binding = binding
        self._documents: dict[str, Any] = {}
        self._modelspaces: dict[str, Any] = {}

    # -- lifecycle ----------------------------------------------------------------------------

    @classmethod
    def launch(
        cls,
        *,
        prog_id: str = PROG_ID,
        visible: bool = True,
        startup_timeout: float = 240.0,
        retry: RetryPolicy | None = None,
        call_timeout: float = 60.0,
    ) -> AutoCADCom:
        """Start a new AutoCAD with ``DispatchEx`` and wait until it is idle.

        Raises :class:`ComStartupError` without retrying: a second launch while the first
        instance may still be starting is exactly what must not happen.
        """
        if sys.platform != "win32":
            raise ComStartupError("AutoCAD COM automation needs Windows")
        if startup_timeout < 180:
            raise ValueError("startup_timeout must be at least 180 s (AutoCAD starts slowly)")
        retry = retry or RetryPolicy()
        before = acad_pids()
        started = time.monotonic()
        deadline = started + startup_timeout
        worker = StaWorker()
        try:
            raw = worker.call(_dispatch_ex, prog_id, timeout=startup_timeout)
        except Exception as exc:
            worker.close()
            new = sorted(acad_pids() - before)
            left = f" acad.exe {new} may still be starting and was left running." if new else ""
            raise ComStartupError(f"could not start {prog_id}: {exc}.{left}") from exc

        startup = RetryPolicy(budget=max(1.0, deadline - time.monotonic()), max_delay=1.0)
        try:
            pid = worker.call(
                _wait_until_ready, raw, before, visible, startup, timeout=startup_timeout
            )
            app, binding = worker.call(_early_bound, raw, retry, timeout=call_timeout)
        except Exception as exc:
            worker.close()
            new = sorted(acad_pids() - before)
            raise ComStartupError(
                f"AutoCAD did not become ready: {exc}. acad.exe {new} was left running; "
                "close it from its window when it has finished starting."
            ) from exc
        return cls(
            worker,
            app,
            pid,
            retry=retry,
            call_timeout=call_timeout,
            startup_seconds=time.monotonic() - started,
            binding=binding,
        )

    def quit(self, timeout: float = 120.0) -> bool:
        """Close every drawing without saving, ``Quit()`` and wait for the process to exit.

        Returns ``False`` (and leaves AutoCAD running) if it did not exit in time.
        """
        from pvsld.transports.pipe import pid_alive

        try:
            self._run(self._close_all_documents, timeout=timeout)
            with contextlib.suppress(Exception):  # the call often fails as the server exits
                self._run(lambda: self._app.Quit(), timeout=timeout)
        except ComError:
            pass
        deadline = time.monotonic() + timeout
        while pid_alive(self.pid) and time.monotonic() < deadline:
            time.sleep(0.5)
        self._worker.close()
        return not pid_alive(self.pid)

    def _close_all_documents(self) -> None:
        documents = self._app.Documents
        for index in reversed(range(documents.Count)):
            documents.Item(index).Close(False)
        self._documents.clear()
        self._modelspaces.clear()

    def _run(self, fn: Callable[..., Any], *args: Any, timeout: float | None = None) -> Any:
        return self._worker.call(fn, *args, timeout=timeout or self.call_timeout)

    # -- documents ----------------------------------------------------------------------------

    def ping(self) -> str:
        """One cross-process round trip (reads ``Application.Version``)."""
        return self._run(lambda: self._app.Version)

    def document_names(self) -> list[str]:
        def names() -> list[str]:
            documents = self._app.Documents
            return [documents.Item(i).Name for i in range(documents.Count)]

        return self._run(names)

    def new_drawing(self) -> str:
        """Create a drawing from the default template, make it current, return its name."""

        def add() -> str:
            document = self._app.Documents.Add()
            name = document.Name
            self._documents[name] = document
            return name

        return self._run(add)

    def close_drawing(self, name: str) -> None:
        """Close one drawing without saving."""

        def close() -> None:
            self._document(name).Close(False)
            self._documents.pop(name, None)
            self._modelspaces.pop(name, None)

        self._run(close)

    def post_command(self, document: str, text: str) -> None:
        """Queue command-line input without waiting for it (``PostCommand``)."""
        self._run(lambda: self._document(document).PostCommand(text))

    def get_variable(self, document: str, name: str) -> Any:
        return self._run(lambda: self._document(document).GetVariable(name))

    def is_quiescent(self) -> bool:
        return self._run(lambda: bool(self._app.GetAcadState().IsQuiescent))

    def _document(self, name: str) -> Any:
        if name not in self._documents:
            documents = self._app.Documents
            for index in range(documents.Count):
                document = documents.Item(index)
                if document.Name.lower() == name.lower():
                    self._documents[name] = document
                    break
            else:
                raise ComError(f"no open drawing named {name!r}")
        return self._documents[name]

    def _modelspace(self, name: str) -> Any:
        if name not in self._modelspaces:
            self._modelspaces[name] = self._document(name).ModelSpace
        return self._modelspaces[name]

    # -- the S2 operations, entity by entity as COM requires ------------------------------------

    def insert_block(
        self,
        document: str,
        block: str,
        position: Sequence[float],
        attributes: Mapping[str, str] | None = None,
    ) -> str:
        """Insert ``block`` (creating the test symbol if missing) and set attributes; a handle."""
        return self._run(self._insert, document, block, position, attributes or {})

    def read_attributes(self, document: str, handle: str) -> dict[str, str]:
        def read() -> dict[str, str]:
            reference = self._document(document).HandleToObject(handle)
            return {a.TagString: a.TextString for a in reference.GetAttributes()}

        return self._run(read)

    def batch(
        self,
        document: str,
        block: str,
        inserts: Iterable[Mapping[str, Any]],
        lines: Iterable[Mapping[str, Any]] = (),
        *,
        timeout: float | None = None,
    ) -> list[str]:
        """The plug-in's ``batch`` done through COM: one call per entity and attribute."""
        inserts = list(inserts)
        lines = list(lines)

        def run() -> list[str]:
            handles = [
                self._insert(document, block, item["position"], item.get("attributes", {}))
                for item in inserts
            ]
            space = self._modelspace(document)
            for line in lines:
                space.AddLine(_point(*line["start"]), _point(*line["end"]))
            return handles

        return self._run(run, timeout=timeout)

    def modelspace_count(self, document: str) -> int:
        return self._run(lambda: int(self._modelspace(document).Count))

    def _insert(
        self, document: str, block: str, position: Sequence[float], attributes: Mapping[str, str]
    ) -> str:
        self._ensure_block(document, block)
        reference = self._modelspace(document).InsertBlock(
            _point(*position), block, 1.0, 1.0, 1.0, 0.0
        )
        values = {key.upper(): value for key, value in attributes.items()}
        for attribute in reference.GetAttributes():
            tag = attribute.TagString
            if tag in values:
                attribute.TextString = values[tag]
        return reference.Handle

    def _ensure_block(self, document: str, block: str) -> None:
        blocks = self._document(document).Blocks
        try:
            blocks.Item(block)
            return
        except ComBusyError:
            raise
        except Exception as exc:  # AutoCAD answers "key not found" with a COM error
            if is_rejected(exc):
                raise
        definition = blocks.Add(_point(0, 0), block)
        outline = definition.AddLightWeightPolyline(_doubles((-10, -5, 10, -5, 10, 5, -10, 5)))
        outline.Closed = True
        definition.AddCircle(_point(0, 0), 3.0)
        definition.AddAttribute(
            2.0, AC_ATTRIBUTE_MODE_INVISIBLE, "Component id", _point(-10, -11), "COMP_ID", ""
        )
        definition.AddAttribute(2.5, AC_ATTRIBUTE_MODE_NORMAL, "Label", _point(-10, 7), "LABEL", "")
        definition.AddAttribute(
            2.0, AC_ATTRIBUTE_MODE_NORMAL, "Rating", _point(-10, -8), "RATING", ""
        )


def _dispatch_ex(prog_id: str) -> Any:
    import win32com.client

    return win32com.client.DispatchEx(prog_id)


def _wait_until_ready(raw: Any, before: set[int], visible: bool, policy: RetryPolicy) -> int:
    """Runs on the STA thread: find the new process, then poll until AutoCAD is quiescent."""
    import win32process

    def hwnd() -> int:
        return raw.HWND

    pid = win32process.GetWindowThreadProcessId(call_with_retry(hwnd, policy, retryable=_starting))[
        1
    ]
    if pid in before:
        raise ComStartupError(
            f"DispatchEx attached to AutoCAD pid {pid}, which was already running; refusing to "
            "drive someone else's session"
        )
    deadline = time.monotonic() + policy.budget
    if visible:
        call_with_retry(lambda: setattr(raw, "Visible", True), policy, retryable=_starting)
    while time.monotonic() < deadline:
        try:
            if raw.GetAcadState().IsQuiescent:
                return pid
        except Exception as exc:
            if not _starting(exc):
                raise
        time.sleep(0.5)
    raise ComStartupError(
        f"AutoCAD pid {pid} was not idle after {policy.budget:.0f} s ({describe_dialogs(pid)})"
    )


def _early_bound(raw: Any, retry: RetryPolicy) -> tuple[RetryingProxy, str]:
    """Switch to makepy (early-bound) wrappers: no per-object type-info round trips."""
    from win32com.client import gencache

    try:
        app = call_with_retry(lambda: gencache.EnsureDispatch(raw._oleobj_), retry)
        binding = "early (makepy)"
    except TypeError:
        app = raw  # makepy unavailable: stay late-bound (slower, still correct)
        binding = "late (dynamic)"
    return RetryingProxy(app, retry), binding
