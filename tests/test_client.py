from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest

from willhaben.client import WillhabenAPIError, WillhabenClient
from willhaben.constants import MARKETPLACE_PATH, X_WH_CLIENT


def make_response(payload: Any = None, status: int = 200) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = payload if payload is not None else {}
    resp.request = MagicMock(spec=httpx.Request)
    return resp


@pytest.fixture
def client() -> WillhabenClient:
    c = WillhabenClient(min_delay=0, max_delay=0, max_retries=2)
    c._http = MagicMock(spec=httpx.Client)
    return c


class TestRequestSuccess:
    def test_returns_parsed_json(self, client: WillhabenClient) -> None:
        client._http.get.return_value = make_response({"hello": "world"})
        result = client.search(MARKETPLACE_PATH, {"keyword": "bike"})
        assert result == {"hello": "world"}

    def test_sets_required_headers(self, client: WillhabenClient) -> None:
        client._http.get.return_value = make_response({})
        client.search(MARKETPLACE_PATH, {"keyword": "bike"})
        headers = client._http.get.call_args.kwargs["headers"]
        assert headers["x-wh-client"] == X_WH_CLIENT
        assert headers["User-Agent"] == client.user_agent
        assert headers["Accept"] == "application/json"
        assert headers["Referer"] == "https://www.willhaben.at/iad"

    def test_sets_isnavigation_default(self, client: WillhabenClient) -> None:
        client._http.get.return_value = make_response({})
        client.search(MARKETPLACE_PATH, {"keyword": "bike"})
        params = client._http.get.call_args.kwargs["params"]
        assert params["isNavigation"] == "true"

    def test_caller_can_override_isnavigation(self, client: WillhabenClient) -> None:
        client._http.get.return_value = make_response({})
        client.search(MARKETPLACE_PATH, {"keyword": "bike", "isNavigation": "false"})
        params = client._http.get.call_args.kwargs["params"]
        assert params["isNavigation"] == "false"

    def test_keyword_passed_through_as_param(self, client: WillhabenClient) -> None:
        client._http.get.return_value = make_response({})
        client.search(MARKETPLACE_PATH, {"keyword": "hello world"})
        params = client._http.get.call_args.kwargs["params"]
        assert params["keyword"] == "hello world"

    def test_list_param_expands_to_repeated_values(
        self, client: WillhabenClient
    ) -> None:
        client._http.get.return_value = make_response({})
        client.search(MARKETPLACE_PATH, {"treeAttributes": [2537, 2540]})
        params = client._http.get.call_args.kwargs["params"]
        assert params["treeAttributes"] == ["2537", "2540"]


class TestRetryBehavior:
    def test_retries_on_429(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.time.sleep"):
            client._http.get.side_effect = [
                make_response({}, status=429),
                make_response({"ok": True}),
            ]
            result = client.search(MARKETPLACE_PATH, {"k": "v"})
        assert result == {"ok": True}
        assert client._http.get.call_count == 2

    def test_retries_on_503(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.time.sleep"):
            client._http.get.side_effect = [
                make_response({}, status=503),
                make_response({"ok": True}),
            ]
            result = client.search(MARKETPLACE_PATH, {"k": "v"})
        assert result == {"ok": True}

    def test_does_not_retry_on_400(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.time.sleep"):
            client._http.get.return_value = make_response({}, status=400)
            with pytest.raises(WillhabenAPIError):
                client.search(MARKETPLACE_PATH, {"k": "v"})
        assert client._http.get.call_count == 1

    def test_raises_after_max_retries(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.time.sleep"):
            client._http.get.return_value = make_response({}, status=503)
            with pytest.raises(WillhabenAPIError):
                client.search(MARKETPLACE_PATH, {"k": "v"})
        assert client._http.get.call_count == 3

    def test_retries_on_request_error(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.time.sleep"):
            client._http.get.side_effect = [
                httpx.ConnectError("network down"),
                make_response({"ok": True}),
            ]
            result = client.search(MARKETPLACE_PATH, {"k": "v"})
        assert result == {"ok": True}

    def test_retries_on_timeout(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.time.sleep"):
            client._http.get.side_effect = [
                httpx.ReadTimeout("timed out"),
                make_response({"ok": True}),
            ]
            result = client.search(MARKETPLACE_PATH, {"k": "v"})
        assert result == {"ok": True}

    def test_retries_on_remote_protocol_error(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.time.sleep"):
            client._http.get.side_effect = [
                httpx.RemoteProtocolError("peer closed connection"),
                make_response({"ok": True}),
            ]
            result = client.search(MARKETPLACE_PATH, {"k": "v"})
        assert result == {"ok": True}

    def test_raises_request_error_after_max_retries(
        self, client: WillhabenClient
    ) -> None:
        with patch("willhaben.client.time.sleep"):
            client._http.get.side_effect = httpx.ConnectError("network down")
            with pytest.raises(WillhabenAPIError):
                client.search(MARKETPLACE_PATH, {"k": "v"})
        assert client._http.get.call_count == 3


class TestPathArgument:
    def test_path_is_joined_onto_api_root(self, client: WillhabenClient) -> None:
        client._http.get.return_value = make_response({})
        client.search("atz/2/131", {"rows": 1})
        url = client._http.get.call_args.args[0]
        assert url.endswith("/restapi/v2/search/atz/2/131")
