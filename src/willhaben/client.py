from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .constants import BASE_URL, DEFAULT_USER_AGENT, X_WH_CLIENT


class WillhabenAPIError(Exception):
    """Raised when the Willhaben API returns an error or unexpected response."""


class WillhabenClient:
    """Thin HTTP client for the Willhaben search JSON API.

    Sets the magic `x-wh-client` header the endpoint requires, throttles
    requests with a polite random delay, and retries transient failures.
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

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "de-AT,de;q=0.9,en;q=0.8",
            "x-wh-client": X_WH_CLIENT,
            "Referer": "https://www.willhaben.at/iad/kaufen-und-verkaufen/marktplatz",
        }

    def _wait(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        delay = random.uniform(self.min_delay, self.max_delay)  # noqa: S311
        if elapsed < delay:
            time.sleep(delay - elapsed)

    def search(self, params: dict[str, str | int]) -> dict[str, Any]:
        query = {k: str(v) for k, v in params.items() if v is not None}
        query.setdefault("isNavigation", "true")
        url = f"{BASE_URL}?{urllib.parse.urlencode(query)}"

        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            self._wait()
            self._last_request_at = time.monotonic()
            req = urllib.request.Request(url, headers=self._headers())  # noqa: S310
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                    body = resp.read()
                return json.loads(body)
            except urllib.error.HTTPError as exc:
                last_exc = exc
                if exc.code in (429, 502, 503, 504) and attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue
                break
            except (urllib.error.URLError, TimeoutError) as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(2**attempt)
                    continue

        raise WillhabenAPIError(f"Request failed: {last_exc!r}") from last_exc
