"""Finding a running bridge from its discovery file."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from pvsld.transports.pipe import (
    DISCOVERY_DIR_ENV,
    BridgeEndpoint,
    PipeClient,
    default_discovery_dir,
    discover_endpoint,
    pid_alive,
)
from pvsld.transports.protocol import BridgeConnectionError


def _write(directory: Path, pid: int, *, protocol: int = 1, mtime: float | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"autocad-{pid}.json"
    path.write_text(
        json.dumps(
            {
                "protocol": protocol,
                "pipe": f"pvsld-acad-{pid}-abc",
                "secret": f"secret-{pid}",
                "pid": pid,
                "server": "pvsld-autocad-bridge 0.2.0",
                "host_version": "26.0",
            }
        ),
        encoding="utf-8",
    )
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def test_discover_prefers_the_newest_live_bridge(tmp_path: Path) -> None:
    _write(tmp_path, 100, mtime=1_000)
    _write(tmp_path, 200, mtime=2_000)
    _write(tmp_path, 300, mtime=3_000)  # newest, but its AutoCAD has exited

    endpoint = discover_endpoint(tmp_path, is_alive=lambda pid: pid in {100, 200})

    assert endpoint.pid == 200
    assert endpoint.pipe == "pvsld-acad-200-abc"
    assert endpoint.secret == "secret-200"
    assert endpoint.path == tmp_path / "autocad-200.json"


def test_discover_by_pid(tmp_path: Path) -> None:
    _write(tmp_path, 100)
    _write(tmp_path, 200)

    assert discover_endpoint(tmp_path, pid=100, is_alive=lambda _: True).pid == 100


def test_only_stale_files_give_an_actionable_error(tmp_path: Path) -> None:
    _write(tmp_path, 300)

    with pytest.raises(BridgeConnectionError, match=r"NETLOAD.*") as caught:
        discover_endpoint(tmp_path, is_alive=lambda _: False)

    assert "autocad-300.json" in str(caught.value)


def test_empty_directory_gives_an_actionable_error(tmp_path: Path) -> None:
    with pytest.raises(BridgeConnectionError, match="Start AutoCAD"):
        discover_endpoint(tmp_path / "missing")


def test_protocol_mismatch_is_refused(tmp_path: Path) -> None:
    path = _write(tmp_path, 100, protocol=99)

    with pytest.raises(BridgeConnectionError, match="protocol 99"):
        BridgeEndpoint.from_file(path)


@pytest.mark.parametrize(
    "content", ["{not json", "[]", '{"pipe": "x"}', '{"pipe":"x","secret":"s","pid":"abc"}']
)
def test_malformed_files_are_refused(tmp_path: Path, content: str) -> None:
    path = tmp_path / "autocad-1.json"
    path.write_text(content, encoding="utf-8")

    with pytest.raises(BridgeConnectionError):
        BridgeEndpoint.from_file(path)


def test_secret_is_not_in_repr(tmp_path: Path) -> None:
    endpoint = BridgeEndpoint.from_file(_write(tmp_path, 100))

    assert "secret-100" not in repr(endpoint)


def test_discovery_dir_honours_override_then_localappdata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(DISCOVERY_DIR_ENV, str(tmp_path / "custom"))
    assert default_discovery_dir() == tmp_path / "custom"

    monkeypatch.delenv(DISCOVERY_DIR_ENV)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))
    assert default_discovery_dir() == tmp_path / "local" / "pvsld" / "bridge"

    monkeypatch.delenv("LOCALAPPDATA")
    assert default_discovery_dir().parts[-2:] == ("pvsld", "bridge")


def test_pid_alive() -> None:
    assert pid_alive(os.getpid())
    assert not pid_alive(0)
    assert not pid_alive(-5)
    assert not pid_alive(2**22 + 12345)  # far above any live pid on CI runners


@pytest.mark.skipif(sys.platform == "win32", reason="checks the non-Windows guard")
def test_named_pipe_client_needs_windows(tmp_path: Path) -> None:
    endpoint = BridgeEndpoint.from_file(_write(tmp_path, 100))

    with pytest.raises(BridgeConnectionError, match="only on Windows"):
        PipeClient.for_endpoint(endpoint)
