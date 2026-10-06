"""S2 safety criteria: rollback on failure, secret handshake, current-user ACLs, allowlist."""

from __future__ import annotations

import dataclasses
import time

import pytest
from s2_support import BLOCK, Results, inserts, lines

pytestmark = pytest.mark.autocad


def _sid_name(sid: object) -> str:
    import win32security

    try:
        name, domain, _ = win32security.LookupAccountSid(None, sid)
        return f"{domain}\\{name}" if domain else name
    except win32security.error:
        return win32security.ConvertSidToStringSid(sid)


def _dacl_summary(descriptor: object) -> dict:
    import win32security

    dacl = descriptor.GetSecurityDescriptorDacl()
    aces = []
    for index in range(dacl.GetAceCount()):
        (ace_type, _flags), mask, sid = dacl.GetAce(index)
        kind = {
            win32security.ACCESS_ALLOWED_ACE_TYPE: "allow",
            win32security.ACCESS_DENIED_ACE_TYPE: "deny",
        }
        aces.append({"type": kind.get(ace_type, str(ace_type)), "mask": hex(mask), "sid": sid})
    control, _revision = descriptor.GetSecurityDescriptorControl()
    return {"aces": aces, "protected": bool(control & win32security.SE_DACL_PROTECTED)}


def _current_user_sid() -> object:
    import win32api
    import win32security

    token = win32security.OpenProcessToken(win32api.GetCurrentProcess(), win32security.TOKEN_QUERY)
    return win32security.GetTokenInformation(token, win32security.TokenUser)[0]


@pytest.mark.parametrize(
    ("block", "fail_after"),
    [(BLOCK, 0), (BLOCK, 150), (BLOCK, 399), (BLOCK, 400), ("PVSLD_S2_ROLLBACK", 200)],
    ids=["before-first", "mid-inserts", "last-line", "before-commit", "new-block-definition"],
)
def test_injected_failure_leaves_the_drawing_unchanged(
    acad, bridge, plugin_drawing: str, results: Results, block: str, fail_after: int
) -> None:
    from pvsld.transports.protocol import BridgeOperationError

    before = bridge.drawing_stats(document=plugin_drawing)
    com_before = acad.modelspace_count(plugin_drawing)

    with pytest.raises(BridgeOperationError) as caught:
        bridge.batch(
            block,
            inserts(200),
            lines(200),
            document=plugin_drawing,
            inject_failure_after=fail_after,
        )

    after = bridge.drawing_stats(document=plugin_drawing)
    results.section("safety").setdefault("injected_failure", []).append(
        {
            "block": block,
            "fail_after_entities": fail_after,
            "rolled_back": caught.value.rolled_back,
            "unchanged": after == before,
            "com_count_unchanged": acad.modelspace_count(plugin_drawing) == com_before,
        }
    )
    assert caught.value.rolled_back
    assert after == before  # same entity handles and the same block definitions
    assert acad.modelspace_count(plugin_drawing) == com_before  # independent check via COM


def test_clients_without_the_secret_are_refused(bridge, plugin, results: Results) -> None:
    from pvsld.transports.pipe import PipeClient
    from pvsld.transports.protocol import BridgeAuthError, LineBuffer, decode, encode, request
    from pvsld.transports.streams import WindowsPipeStream

    stream = WindowsPipeStream.connect(plugin.pipe, 5, expected_server_pid=plugin.pid)
    try:
        stream.send(encode(request(1, "insert_block", {"block": BLOCK, "position": [0, 0]})), 5)
        buffer, reply = LineBuffer(), []
        while not reply:
            reply = buffer.feed(stream.recv(4096, 5))
        refusal = decode(reply[0])
        hung_up = stream.recv(4096, 5) == b""
    finally:
        stream.close()

    impostor = PipeClient.for_endpoint(dataclasses.replace(plugin, secret="not-the-secret"))
    with pytest.raises(BridgeAuthError):
        impostor.connect()

    silent = WindowsPipeStream.connect(plugin.pipe, 5, expected_server_pid=plugin.pid)
    started = time.monotonic()
    try:
        buffer, reply = LineBuffer(), []
        while not reply:
            chunk = silent.recv(4096, 10)
            if not chunk:
                break
            reply = buffer.feed(chunk)
        silent_dropped_s = round(time.monotonic() - started, 2)
    finally:
        silent.close()

    results.section("safety")["unauthenticated"] = {
        "no_auth_error": refusal["error"],
        "connection_closed": hung_up,
        "wrong_secret": "refused (BridgeAuthError)",
        "silent_client_dropped_after_s": silent_dropped_s,
    }
    assert refusal["error"]["code"] == -32001
    assert hung_up
    assert bridge.ping()["pong"] is True  # the real client is unaffected


def test_pipe_acl_admits_only_the_current_user(plugin, results: Results) -> None:
    import win32security

    from pvsld.transports.streams import WindowsPipeStream

    stream = WindowsPipeStream.connect(plugin.pipe, 5, expected_server_pid=plugin.pid)
    try:
        descriptor = win32security.GetSecurityInfo(
            stream.handle,
            win32security.SE_KERNEL_OBJECT,
            win32security.DACL_SECURITY_INFORMATION | win32security.OWNER_SECURITY_INFORMATION,
        )
    finally:
        stream.close()
    summary = _dacl_summary(descriptor)
    me = _current_user_sid()
    network = win32security.CreateWellKnownSid(win32security.WinNetworkSid)

    results.section("safety")["pipe_acl"] = {
        "protected": summary["protected"],
        "aces": [{**ace, "sid": _sid_name(ace["sid"])} for ace in summary["aces"]],
        "owner": _sid_name(descriptor.GetSecurityDescriptorOwner()),
    }
    allowed = [ace["sid"] for ace in summary["aces"] if ace["type"] == "allow"]
    denied = [ace["sid"] for ace in summary["aces"] if ace["type"] == "deny"]
    assert allowed == [me]
    assert network in denied
    assert summary["protected"]


def test_secret_file_is_readable_only_by_the_current_user(plugin, results: Results) -> None:
    import win32security

    descriptor = win32security.GetFileSecurity(
        str(plugin.path), win32security.DACL_SECURITY_INFORMATION
    )
    summary = _dacl_summary(descriptor)

    results.section("safety")["secret_file_acl"] = {
        "path": str(plugin.path),
        "protected": summary["protected"],
        "aces": [{**ace, "sid": _sid_name(ace["sid"])} for ace in summary["aces"]],
    }
    assert [ace["sid"] for ace in summary["aces"]] == [_current_user_sid()]
    assert summary["protected"]


def test_methods_outside_the_allowlist_are_refused(bridge) -> None:
    from pvsld.transports.protocol import BridgeRemoteError, ErrorCode

    with pytest.raises(BridgeRemoteError) as caught:
        bridge.call("execute_lisp", {"code": '(command "_.ERASE" "_ALL" "")'})

    assert caught.value.code == ErrorCode.METHOD_NOT_FOUND
