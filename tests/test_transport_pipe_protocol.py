"""Wire-format helpers of the bridge protocol (no I/O)."""

from __future__ import annotations

import json

import pytest

from pvsld.transports.protocol import (
    METHODS,
    BridgeAuthError,
    BridgeBusyError,
    BridgeOperationError,
    BridgeProtocolError,
    BridgeRemoteError,
    ErrorCode,
    LineBuffer,
    decode,
    encode,
    error_from_payload,
    error_response,
    request,
    result_response,
)


def test_encode_is_one_compact_line_even_with_newlines_and_accents() -> None:
    data = encode(request(1, "insert_block", {"attributes": {"LABEL": "Línea\nnueva"}}))

    assert data.endswith(b"\n")
    assert data.count(b"\n") == 1
    assert json.loads(data)["params"]["attributes"]["LABEL"] == "Línea\nnueva"


def test_request_omits_params_when_none() -> None:
    assert request(3, "ping") == {"jsonrpc": "2.0", "id": 3, "method": "ping"}


def test_decode_round_trips_and_rejects_non_objects() -> None:
    message = result_response(5, {"pong": True})

    assert decode(encode(message)) == message
    with pytest.raises(BridgeProtocolError):
        decode(b"[1, 2]")
    with pytest.raises(BridgeProtocolError):
        decode(b"{not json")
    with pytest.raises(BridgeProtocolError):
        decode(b"\xff\xfe")


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        (ErrorCode.UNAUTHORIZED, BridgeAuthError),
        (ErrorCode.BUSY, BridgeBusyError),
        (ErrorCode.OPERATION_FAILED, BridgeOperationError),
        (ErrorCode.INVALID_PARAMS, BridgeRemoteError),
        (ErrorCode.METHOD_NOT_FOUND, BridgeRemoteError),
    ],
)
def test_error_from_payload_maps_codes_to_exceptions(code: int, expected: type) -> None:
    error = error_from_payload(error_response(1, code, "boom", {"x": 1})["error"])

    assert type(error) is expected
    assert error.code == code
    assert error.data == {"x": 1}
    assert str(error) == f"[{int(code)}] boom"


def test_busy_error_exposes_reason_and_retry_after() -> None:
    error = error_from_payload(
        {
            "code": -32002,
            "message": "close it",
            "data": {"reason": "modal_dialog", "retry_after_ms": 2500},
        }
    )

    assert isinstance(error, BridgeBusyError)
    assert error.reason == "modal_dialog"
    assert error.retry_after == 2.5


def test_operation_error_reports_rollback() -> None:
    error = error_from_payload({"code": -32003, "message": "x", "data": {"rolled_back": True}})

    assert isinstance(error, BridgeOperationError)
    assert error.rolled_back


def test_error_from_payload_rejects_malformed_errors() -> None:
    with pytest.raises(BridgeProtocolError):
        error_from_payload({"message": "no code"})
    with pytest.raises(BridgeProtocolError):
        error_from_payload("boom")


def test_line_buffer_reassembles_chunks_and_strips_cr() -> None:
    buffer = LineBuffer()

    assert buffer.feed(b'{"a":') == []
    assert buffer.feed(b'1}\r\n{"b":2}\n{"c"') == [b'{"a":1}', b'{"b":2}']
    assert buffer.feed(b":3}\n") == [b'{"c":3}']


def test_line_buffer_refuses_oversized_lines() -> None:
    buffer = LineBuffer(max_line_bytes=8)

    with pytest.raises(BridgeProtocolError):
        buffer.feed(b"x" * 9)
    with pytest.raises(BridgeProtocolError):
        LineBuffer(max_line_bytes=8).feed(b"y" * 12 + b"\n")


def test_allowlist_has_no_code_execution_methods() -> None:
    assert set(METHODS) == {
        "auth",
        "ping",
        "insert_block",
        "read_attributes",
        "batch",
        "drawing_stats",
    }
