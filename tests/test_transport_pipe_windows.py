"""The client over a real Windows named pipe, against the in-process fake bridge."""

from __future__ import annotations

import os
import secrets
import sys
import time
from collections.abc import Iterator

import pytest

from pvsld.transports.fake import FakeBridgeServer
from pvsld.transports.pipe import BridgeEndpoint, PipeClient
from pvsld.transports.protocol import (
    BridgeAuthError,
    BridgeConnectionError,
    BridgeTimeoutError,
)

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="named pipes are Windows-only")

SECRET = "pipe-test-secret"


@pytest.fixture
def pipe_name() -> str:
    return f"pvsld-test-{os.getpid()}-{secrets.token_hex(4)}"


@pytest.fixture
def fake(pipe_name: str) -> Iterator[FakeBridgeServer]:
    server = FakeBridgeServer(SECRET, auth_timeout=1.0)
    server.listen_pipe(pipe_name)
    yield server
    server.stop()


def _endpoint(pipe_name: str, *, pid: int | None = None, secret: str = SECRET) -> BridgeEndpoint:
    return BridgeEndpoint(pipe=pipe_name, secret=secret, pid=pid or os.getpid())


def test_round_trip_over_a_named_pipe(fake: FakeBridgeServer, pipe_name: str) -> None:
    with PipeClient.for_endpoint(_endpoint(pipe_name)) as client:
        inserted = client.insert_block("PVSLD_S2_TEST", [1, 2], {"COMP_ID": "PV-1"})
        batch = client.batch(
            "PVSLD_S2_TEST",
            [{"position": [i, 0], "attributes": {"LABEL": "ñandú"}} for i in range(50)],
            [{"start": [0, 0], "end": [1, 1]}] * 50,
        )
        attributes = client.read_attributes(handle=batch["handles"][-1])[0]["attributes"]

    assert inserted["attributes"]["COMP_ID"] == "PV-1"
    assert batch["inserted"] == 50
    assert attributes["LABEL"] == "ñandú"


def test_large_messages_cross_the_pipe(fake: FakeBridgeServer, pipe_name: str) -> None:
    inserts = [{"position": [i, 0], "attributes": {"LABEL": "x" * 200}} for i in range(2000)]

    with PipeClient.for_endpoint(_endpoint(pipe_name)) as client:
        result = client.batch("BIG", inserts)

    assert len(result["handles"]) == 2000


def test_wrong_secret_is_refused(fake: FakeBridgeServer, pipe_name: str) -> None:
    client = PipeClient.for_endpoint(_endpoint(pipe_name, secret="nope"))

    with pytest.raises(BridgeAuthError):
        client.connect()
    assert fake.auth_failures == 1


def test_missing_pipe_fails_fast_with_guidance(pipe_name: str) -> None:
    from pvsld.transports.streams import WindowsPipeStream

    started = time.monotonic()

    with pytest.raises(BridgeConnectionError, match="NETLOAD"):
        WindowsPipeStream.connect(pipe_name + "-absent", timeout=5)

    assert time.monotonic() - started < 2


def test_pipe_served_by_another_process_is_not_trusted(
    fake: FakeBridgeServer, pipe_name: str
) -> None:
    client = PipeClient.for_endpoint(_endpoint(pipe_name, pid=os.getpid() + 1))

    with pytest.raises(BridgeConnectionError, match="refusing to send the secret"):
        client.connect()
    assert fake.auth_failures == 0  # the secret never left this process


def test_read_timeout_on_a_silent_server(fake: FakeBridgeServer, pipe_name: str) -> None:
    client = PipeClient.for_endpoint(_endpoint(pipe_name))
    client.connect()
    fake.delay = 0.6

    with pytest.raises(BridgeTimeoutError):
        client.ping(timeout=0.15)

    fake.delay = 0.0
    assert client.ping()["pong"] is True
    client.close()


def test_server_hang_up_is_detected(fake: FakeBridgeServer, pipe_name: str) -> None:
    client = PipeClient.for_endpoint(_endpoint(pipe_name))
    client.connect()
    fake.close_after = 1
    client.ping()

    with pytest.raises(BridgeConnectionError):
        client.ping()
    client.close()
