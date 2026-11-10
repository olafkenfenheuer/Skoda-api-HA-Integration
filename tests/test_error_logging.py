"""Tests for the details kept from an error response of the API."""

from __future__ import annotations

import json
import logging

from custom_components.skoda_api_connect.api import SkodaApi

VIN = "TMBJJ7NX0LY000001"
PATH = f"/api/v1/vehicles/{VIN}/auxiliary-heating/start"


class _Response:
    """The parts of an aiohttp response that the error handling reads."""

    def __init__(self, status: int, body: dict | str, headers: dict[str, str] | None = None):
        self.status = status
        self.headers = headers or {}
        self._text = body if isinstance(body, str) else json.dumps(body)

    async def text(self) -> str:
        return self._text


async def test_server_error_keeps_trace_id_and_logs_the_response(caplog) -> None:
    body = {"type": "about:blank", "title": "Internal Server Error", "status": 500}
    with caplog.at_level(logging.WARNING):
        err = await SkodaApi._error_for(
            _Response(500, body, {"traceid": "abc123"}), "POST", PATH
        )
    assert err.status == 500
    assert err.trace_id == "abc123"
    assert str(err) == "Internal Server Error (HTTP 500, trace id abc123)"
    assert "HTTP 500" in caplog.text
    assert "trace id abc123" in caplog.text
    assert "Internal Server Error" in caplog.text
    # The VIN is shortened in the log.
    assert VIN not in caplog.text
    assert "/vehicles/...0001/auxiliary-heating/start" in caplog.text


async def test_client_error_message_is_unchanged(caplog) -> None:
    body = {
        "type": "https://public.api.connect.skoda-auto.cz/problems/operation-not-supported",
        "detail": "Not supported",
    }
    with caplog.at_level(logging.WARNING):
        err = await SkodaApi._error_for(_Response(422, body, {"traceid": "t"}), "POST", PATH)
    assert str(err) == "Not supported"
    assert err.problem == "operation-not-supported"
    assert "operation-not-supported" in caplog.text


async def test_server_error_without_trace_id_or_json(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        err = await SkodaApi._error_for(_Response(502, "<html>Bad Gateway</html>"), "GET", PATH)
    assert str(err) == "HTTP 502"
    assert err.trace_id is None
    assert "Bad Gateway" in caplog.text


async def test_long_body_is_cut_in_the_log(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        await SkodaApi._error_for(_Response(500, "x" * 5000), "GET", PATH)
    assert "x" * 500 in caplog.text
    assert "x" * 501 not in caplog.text
