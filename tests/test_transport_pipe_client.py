"""Protocol tests of the bridge client against the in-process fake plug-in (any OS, no AutoCAD)."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Callable, Iterator

import pytest

from pvsld.transports.fake import FakeBridgeServer
from pvsld.transports.pipe import PipeClient
from pvsld.transports.protocol import (
    BridgeAuthError,
    BridgeBusyError,
    BridgeConnectionError,
    BridgeOperationError,
    BridgeProtocolError,
    BridgeRemoteError,
    BridgeTimeoutError,
    ErrorCode,
    decode,
    encode,
    request,
)
from pvsld.transports.streams import SocketStream

SECRET = "correct-horse-battery-staple"
BLOCK = "PVSLD_S2_TEST"


@pytest.fixture
def fake() -> Iterator[FakeBridgeServer]:
    server = FakeBridgeServer(SECRET, documents=("Drawing1.dwg", "Other.dwg"), auth_timeout=0.5)
    yield server
    server.stop()


@pytest.fixture
def address(fake: FakeBridgeServer) -> tuple[str, int]:
    return fake.listen_tcp()


@pytest.fixture
def connect(address: tuple[str, int]) -> Iterator[Callable[..., PipeClient]]:
    clients: list[PipeClient] = []

    def make(secret: str = SECRET, **kwargs: float) -> PipeClient:
        host, port = address
        client = PipeClient(lambda t: SocketStream.connect(host, port, t), secret, **kwargs)
        clients.append(client)
        return client

    yield make
    for client in clients:
        client.close()


def _raw(address: tuple[str, int]) -> socket.socket:
    sock = socket.create_connection(address, timeout=5)
    sock.settimeout(5)
    return sock


def _read_line(sock: socket.socket) -> bytes:
    data = b""
    while not data.endswith(b"\n"):
        chunk = sock.recv(4096)
        if not chunk:
            return data
        data += chunk
    return data


def _inserts(count: int) -> list[dict]:
    return [
        {"position": [i * 30.0, 0.0], "attributes": {"COMP_ID": f"PV-{i}", "LABEL": f"Módulo {i}"}}
        for i in range(count)
    ]


def _lines(count: int) -> list[dict]:
    return [{"start": [i * 30.0, -20.0], "end": [i * 30.0 + 20.0, -20.0]} for i in range(count)]


# -- authentication ---------------------------------------------------------------------------


def test_connect_authenticates_and_returns_hello(connect: Callable[..., PipeClient]) -> None:
    client = connect()

    hello = client.connect()

    assert client.connected
    assert hello["protocol"] == 1
    assert "batch" in hello["methods"]
    assert client.ping()["pong"] is True


def test_wrong_secret_is_refused_and_connection_dropped(
    connect: Callable[..., PipeClient], fake: FakeBridgeServer
) -> None:
    client = connect(secret="guess")

    with pytest.raises(BridgeAuthError, match="unauthorized"):
        client.connect()

    assert not client.connected
    assert fake.auth_failures == 1
    assert fake.methods_seen == []


def test_raw_client_without_auth_is_refused(
    address: tuple[str, int], fake: FakeBridgeServer
) -> None:
    with _raw(address) as sock:
        sock.sendall(encode(request(1, "insert_block", {"block": BLOCK, "position": [0, 0]})))

        refusal = decode(_read_line(sock))

        assert refusal["error"]["code"] == ErrorCode.UNAUTHORIZED
        assert _read_line(sock) == b""  # the server hung up
    assert fake.methods_seen == []


def test_silent_client_is_disconnected_after_auth_timeout(address: tuple[str, int]) -> None:
    with _raw(address) as sock:
        started = time.monotonic()

        refusal = decode(_read_line(sock))

        assert refusal["error"]["code"] == ErrorCode.UNAUTHORIZED
        assert "timed out" in refusal["error"]["message"]
        assert time.monotonic() - started < 3
        assert _read_line(sock) == b""


def test_garbage_before_auth_is_refused(address: tuple[str, int]) -> None:
    with _raw(address) as sock:
        sock.sendall(b"hello there\n")

        assert decode(_read_line(sock))["error"]["code"] == ErrorCode.PARSE_ERROR
        assert _read_line(sock) == b""


# -- operations -------------------------------------------------------------------------------


def test_insert_and_read_back_attributes(connect: Callable[..., PipeClient]) -> None:
    client = connect()
    attributes = {"COMP_ID": "INV-1", "LABEL": "Inversor 6 kW", "RATING": "220 V"}

    inserted = client.insert_block(BLOCK, [10, 20], attributes)
    by_handle = client.read_attributes(handle=inserted["handle"])
    by_block = client.read_attributes(block=BLOCK)

    assert inserted["created_block_definition"] is True
    assert inserted["attributes"] == attributes
    assert by_handle[0]["attributes"] == attributes
    assert by_handle[0]["position"] == [10.0, 20.0, 0.0]
    assert [r["handle"] for r in by_block] == [inserted["handle"]]


def test_attribute_tags_are_case_insensitive(connect: Callable[..., PipeClient]) -> None:
    client = connect()

    inserted = client.insert_block(BLOCK, [0, 0], {"comp_id": "X-1"})

    assert inserted["attributes"]["COMP_ID"] == "X-1"


def test_unknown_attribute_tag_is_rejected_without_changes(
    connect: Callable[..., PipeClient],
) -> None:
    client = connect()
    before = client.drawing_stats()

    with pytest.raises(BridgeRemoteError) as caught:
        client.insert_block(BLOCK, [0, 0], {"NOT_A_TAG": "x"})

    assert caught.value.code == ErrorCode.INVALID_PARAMS
    assert "COMP_ID" in caught.value.message  # the error lists the valid tags
    assert client.drawing_stats() == before


def test_batch_creates_inserts_and_lines_in_one_call(connect: Callable[..., PipeClient]) -> None:
    client = connect()

    result = client.batch(BLOCK, _inserts(200), _lines(200))
    stats = client.drawing_stats()

    assert (result["inserted"], result["lines"]) == (200, 200)
    assert len(set(result["handles"])) == 200
    assert stats["modelspace_entities"] == 400
    assert stats["block_definitions"] == [BLOCK]
    assert client.read_attributes(handle=result["handles"][7])[0]["attributes"]["COMP_ID"] == "PV-7"


@pytest.mark.parametrize("fail_after", [0, 150, 400])
def test_injected_failure_rolls_back_everything(
    connect: Callable[..., PipeClient], fail_after: int
) -> None:
    client = connect()
    client.insert_block("EXISTING", [0, 0])
    before = client.drawing_stats()

    with pytest.raises(BridgeOperationError) as caught:
        client.batch("NEW_BLOCK", _inserts(200), _lines(200), inject_failure_after=fail_after)

    assert caught.value.rolled_back
    assert client.drawing_stats() == before  # no entity and no new block definition survived


def test_busy_error_is_actionable_and_connection_survives(
    connect: Callable[..., PipeClient], fake: FakeBridgeServer
) -> None:
    client = connect()
    client.connect()
    fake.busy = ("modal_dialog", "A modal dialog is open in AutoCAD. Close it, then retry.")

    with pytest.raises(BridgeBusyError) as caught:
        client.insert_block(BLOCK, [0, 0])

    assert caught.value.reason == "modal_dialog"
    assert "Close it" in caught.value.message
    assert caught.value.retry_after == 1.0
    assert client.connected
    assert client.ping()["pong"] is True  # a transport ping still answers while AutoCAD is busy
    fake.busy = None
    assert client.insert_block(BLOCK, [0, 0])["handle"]


def test_main_thread_ping_reports_unavailable_main_thread(
    connect: Callable[..., PipeClient], fake: FakeBridgeServer
) -> None:
    client = connect()
    fake.busy = ("main_thread_unavailable", "AutoCAD did not accept the request in time.")

    with pytest.raises(BridgeBusyError):
        client.ping(main_thread=True)
    assert client.ping()["main_thread"] is False


def test_documents_are_addressed_by_name(connect: Callable[..., PipeClient]) -> None:
    client = connect()

    client.insert_block(BLOCK, [0, 0], document="other.dwg")

    assert client.drawing_stats(document="Other.dwg")["modelspace_entities"] == 1
    assert client.drawing_stats()["modelspace_entities"] == 0
    with pytest.raises(BridgeRemoteError) as caught:
        client.drawing_stats(document="Missing.dwg")
    assert caught.value.code == ErrorCode.DOCUMENT_NOT_FOUND
    assert "Other.dwg" in caught.value.message


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("insert_block", {"block": "bad name!", "position": [0, 0]}),
        ("insert_block", {"block": BLOCK, "position": [0]}),
        ("insert_block", {"block": BLOCK, "position": [0, "1"]}),
        ("insert_block", {"block": BLOCK, "position": [0, 0], "attributes": {"LABEL": 5}}),
        ("read_attributes", {}),
        ("read_attributes", {"handle": "ZZZ"}),
        ("batch", {"block": BLOCK, "inserts": "many"}),
        ("batch", {"block": BLOCK, "inject_failure_after": -1}),
        ("ping", {"main_thread": "yes"}),
    ],
)
def test_invalid_params_are_reported(
    connect: Callable[..., PipeClient], method: str, params: dict
) -> None:
    client = connect()

    with pytest.raises(BridgeRemoteError) as caught:
        client.call(method, params)

    assert caught.value.code == ErrorCode.INVALID_PARAMS


def test_methods_outside_the_allowlist_are_refused(connect: Callable[..., PipeClient]) -> None:
    client = connect()

    with pytest.raises(BridgeRemoteError) as caught:
        client.call("execute_lisp", {"code": '(command "_.ERASE" "_ALL" "")'})

    assert caught.value.code == ErrorCode.METHOD_NOT_FOUND


# -- timeouts and failures ----------------------------------------------------------------------


def test_timeout_drops_connection_and_next_call_reconnects(
    connect: Callable[..., PipeClient], fake: FakeBridgeServer
) -> None:
    client = connect()
    client.connect()
    fake.delay = 0.5
    started = time.monotonic()

    with pytest.raises(BridgeTimeoutError):
        client.ping(timeout=0.1)

    assert time.monotonic() - started < 0.4
    assert not client.connected
    fake.delay = 0.0
    assert client.ping()["pong"] is True
    assert client.connected


def test_server_hanging_up_is_reported_then_recovered(
    connect: Callable[..., PipeClient], fake: FakeBridgeServer
) -> None:
    client = connect()
    fake.close_after = 1
    client.ping()

    with pytest.raises(BridgeConnectionError):
        client.ping()

    fake.close_after = None
    assert client.ping()["pong"] is True


def test_connection_refused_is_a_connection_error() -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]  # nothing listens here once the probe closes
    client = PipeClient(lambda t: SocketStream.connect("127.0.0.1", port, t), SECRET)

    with pytest.raises(BridgeConnectionError):
        client.connect()


def test_context_manager_connects_and_closes(connect: Callable[..., PipeClient]) -> None:
    client = connect()

    with client as session:
        assert session.connected

    assert not client.connected


# -- a scripted peer for malformed responses ----------------------------------------------------


@pytest.fixture
def scripted() -> Iterator[Callable[[list[bytes]], tuple[str, int]]]:
    """A peer that answers every request line with the next scripted reply (or hangs up)."""
    servers: list[socket.socket] = []

    def start(replies: list[bytes]) -> tuple[str, int]:
        server = socket.create_server(("127.0.0.1", 0))
        servers.append(server)

        def run() -> None:
            conn, _ = server.accept()
            with conn:
                for reply in replies:
                    if not _read_line(conn):
                        return
                    conn.sendall(reply)

        threading.Thread(target=run, daemon=True).start()
        return server.getsockname()[:2]

    yield start
    for server in servers:
        server.close()


def _scripted_client(address: tuple[str, int]) -> PipeClient:
    host, port = address
    return PipeClient(lambda t: SocketStream.connect(host, port, t), SECRET, timeout=2)


HELLO = b'{"jsonrpc":"2.0","id":1,"result":{"protocol":1}}\n'


def test_non_json_reply_is_a_protocol_error(scripted: Callable[..., tuple[str, int]]) -> None:
    client = _scripted_client(scripted([HELLO, b"<html>oops</html>\n"]))
    client.connect()

    with pytest.raises(BridgeProtocolError):
        client.ping()
    assert not client.connected


def test_reply_without_result_is_a_protocol_error(scripted: Callable[..., tuple[str, int]]) -> None:
    client = _scripted_client(scripted([HELLO, b'{"jsonrpc":"2.0","id":2}\n']))
    client.connect()

    with pytest.raises(BridgeProtocolError):
        client.ping()


def test_replies_for_other_ids_are_skipped(scripted: Callable[..., tuple[str, int]]) -> None:
    reply = b'{"jsonrpc":"2.0","id":99,"result":"stale"}\n{"jsonrpc":"2.0","id":2,"result":"ok"}\n'
    client = _scripted_client(scripted([HELLO, reply]))
    client.connect()

    assert client.call("ping") == "ok"


def test_error_without_id_is_raised(scripted: Callable[..., tuple[str, int]]) -> None:
    refusal = b'{"jsonrpc":"2.0","id":null,"error":{"code":-32001,"message":"auth timed out"}}\n'
    client = _scripted_client(scripted([refusal]))

    with pytest.raises(BridgeAuthError):
        client.connect()
