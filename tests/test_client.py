from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

import pytest

from willhaben.client import WillhabenAPIError, WillhabenClient
from willhaben.constants import MARKETPLACE_PATH, X_WH_CLIENT


def make_urlopen_response(payload: dict[str, Any]) -> MagicMock:
    """Build a context-manager mock that mimics urllib's response."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    cm = MagicMock()
    cm.__enter__.return_value = resp
    cm.__exit__.return_value = None
    return cm


def make_http_error(code: int) -> HTTPError:
    return HTTPError(
        url="http://example",
        code=code,
        msg="err",
        hdrs=None,  # type: ignore[arg-type]
        fp=None,
    )


@pytest.fixture
def client() -> WillhabenClient:
    return WillhabenClient(min_delay=0, max_delay=0, max_retries=2)


class TestRequestSuccess:
    def test_returns_parsed_json(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.urllib.request.urlopen") as urlopen:
            urlopen.return_value = make_urlopen_response({"hello": "world"})
            result = client.search(MARKETPLACE_PATH, {"keyword": "bike"})
        assert result == {"hello": "world"}

    def test_sets_required_headers(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.urllib.request.urlopen") as urlopen:
            urlopen.return_value = make_urlopen_response({})
            client.search(MARKETPLACE_PATH, {"keyword": "bike"})
        req = urlopen.call_args.args[0]
        assert req.get_header("X-wh-client") == X_WH_CLIENT
        assert req.get_header("User-agent") == client.user_agent
        assert req.get_header("Accept") == "application/json"
        assert req.get_header("Referer") == "https://www.willhaben.at/iad"

    def test_sets_isnavigation_default(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.urllib.request.urlopen") as urlopen:
            urlopen.return_value = make_urlopen_response({})
            client.search(MARKETPLACE_PATH, {"keyword": "bike"})
        req = urlopen.call_args.args[0]
        assert "isNavigation=true" in req.full_url

    def test_caller_can_override_isnavigation(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.urllib.request.urlopen") as urlopen:
            urlopen.return_value = make_urlopen_response({})
            client.search(MARKETPLACE_PATH, {"keyword": "bike", "isNavigation": "false"})
        req = urlopen.call_args.args[0]
        assert "isNavigation=false" in req.full_url

    def test_keyword_is_url_encoded(self, client: WillhabenClient) -> None:
        with patch("willhaben.client.urllib.request.urlopen") as urlopen:
            urlopen.return_value = make_urlopen_response({})
            client.search(MARKETPLACE_PATH, {"keyword": "hello world"})
        req = urlopen.call_args.args[0]
        assert "keyword=hello+world" in req.full_url


class TestRetryBehavior:
    def test_retries_on_429(self, client: WillhabenClient) -> None:
        with (
            patch("willhaben.client.urllib.request.urlopen") as urlopen,
            patch("willhaben.client.time.sleep"),
        ):
            urlopen.side_effect = [
                make_http_error(429),
                make_urlopen_response({"ok": True}),
            ]
            result = client.search(MARKETPLACE_PATH, {"k": "v"})
        assert result == {"ok": True}
        assert urlopen.call_count == 2

    def test_retries_on_503(self, client: WillhabenClient) -> None:
        with (
            patch("willhaben.client.urllib.request.urlopen") as urlopen,
            patch("willhaben.client.time.sleep"),
        ):
            urlopen.side_effect = [
                make_http_error(503),
                make_urlopen_response({"ok": True}),
            ]
            result = client.search(MARKETPLACE_PATH, {"k": "v"})
        assert result == {"ok": True}

    def test_does_not_retry_on_400(self, client: WillhabenClient) -> None:
        with (
            patch("willhaben.client.urllib.request.urlopen") as urlopen,
            patch("willhaben.client.time.sleep"),
        ):
            urlopen.side_effect = make_http_error(400)
            with pytest.raises(WillhabenAPIError):
                client.search(MARKETPLACE_PATH, {"k": "v"})
        assert urlopen.call_count == 1

    def test_raises_after_max_retries(self, client: WillhabenClient) -> None:
        with (
            patch("willhaben.client.urllib.request.urlopen") as urlopen,
            patch("willhaben.client.time.sleep"),
        ):
            urlopen.side_effect = make_http_error(503)
            with pytest.raises(WillhabenAPIError):
                client.search(MARKETPLACE_PATH, {"k": "v"})
        assert urlopen.call_count == 3

    def test_retries_on_urlerror(self, client: WillhabenClient) -> None:
        with (
            patch("willhaben.client.urllib.request.urlopen") as urlopen,
            patch("willhaben.client.time.sleep"),
        ):
            urlopen.side_effect = [
                URLError("network down"),
                make_urlopen_response({"ok": True}),
            ]
            result = client.search(MARKETPLACE_PATH, {"k": "v"})
        assert result == {"ok": True}

    def test_retries_on_timeout(self, client: WillhabenClient) -> None:
        with (
            patch("willhaben.client.urllib.request.urlopen") as urlopen,
            patch("willhaben.client.time.sleep"),
        ):
            urlopen.side_effect = [
                TimeoutError("timed out"),
                make_urlopen_response({"ok": True}),
            ]
            result = client.search(MARKETPLACE_PATH, {"k": "v"})
        assert result == {"ok": True}

    def test_raises_urlerror_after_max_retries(
        self, client: WillhabenClient
    ) -> None:
        with (
            patch("willhaben.client.urllib.request.urlopen") as urlopen,
            patch("willhaben.client.time.sleep"),
        ):
            urlopen.side_effect = URLError("network down")
            with pytest.raises(WillhabenAPIError):
                client.search(MARKETPLACE_PATH, {"k": "v"})
        assert urlopen.call_count == 3


class TestPathArgument:
    def test_path_is_joined_onto_api_root(
        self, client: WillhabenClient
    ) -> None:
        with patch("willhaben.client.urllib.request.urlopen") as urlopen:
            urlopen.return_value = make_urlopen_response({})
            client.search("atz/2/131", {"rows": 1})
        req = urlopen.call_args.args[0]
        assert "/webapi/iad/search/atz/2/131?" in req.full_url
