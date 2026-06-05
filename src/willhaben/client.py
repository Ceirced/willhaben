from __future__ import annotations

import random
import time
from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from .constants import API_ROOT, DEFAULT_USER_AGENT, X_WH_CLIENT

QueryValue = str | int | Sequence[int | str]
"""A query parameter value: a scalar, or a sequence of ids that becomes repeated
query keys (e.g. ``treeAttributes=2537&treeAttributes=2540``). A sequence accepts
both ints and the string ids that `navigation.FilterValue.value` hands back."""
QueryParams = Mapping[str, QueryValue]


class WillhabenAPIError(Exception):
    """Raised when the Willhaben API returns an error or unexpected response."""


_RETRY_STATUS = {429, 502, 503, 504}


class WillhabenClient:
    """Thin HTTP client for the Willhaben search JSON API.

    Sets the magic `x-wh-client` header the endpoint requires, throttles
    requests with a polite random delay, and retries transient failures.
    Uses httpx with HTTP/2 — stdlib http.client's chunked decoder fails
    intermittently on willhaben's larger uncompressed responses.
    """

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        min_delay: float = 0.5,
        max_delay: float = 1.5,
        timeout: float = 15.0,
        max_retries: int = 2,
    ) -> None:
        self.user_agent = user_agent
        self.min_delay = min_delay
        self.max_delay = max_delay
        self.timeout = timeout
        self.max_retries = max_retries
        self._last_request_at: float = 0.0
        self._http = httpx.Client(http2=True, timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
            "x-wh-client": X_WH_CLIENT,
            "Referer": "https://www.willhaben.at/iad",
        }

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        delay = random.uniform(self.min_delay, self.max_delay)  # noqa: S311
        if elapsed < delay:
            time.sleep(delay - elapsed)

    def search(
        self, path: str, params: QueryParams
    ) -> dict[str, Any]:
        query: dict[str, str | list[str]] = {}
        for key, value in params.items():
            if value is None:
                continue
            if isinstance(value, (list, tuple)):
                query[key] = [str(v) for v in value]
            else:
                query[key] = str(value)
        query.setdefault("isNavigation", "true")
        url = f"{API_ROOT}/{path}"

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._wait()
            self._last_request_at = time.monotonic()
            try:
                resp = self._http.get(url, params=query, headers=self._headers())
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                break
            if resp.status_code in _RETRY_STATUS and attempt < self.max_retries:
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
                time.sleep(2**attempt)
                continue
            if resp.status_code >= 400:
                last_exc = httpx.HTTPStatusError(
                    f"{resp.status_code}", request=resp.request, response=resp
                )
                break
            return resp.json()

        raise WillhabenAPIError(f"Request failed: {last_exc!r}") from last_exc
