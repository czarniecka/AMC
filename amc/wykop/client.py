"""Wykop API v3 (https://doc.wykop.pl) with an application token; no site pages are fetched.

The API is served under /api/v3, which Wykop's robots.txt disallows for crawlers. We treat
robots.txt as addressed to page crawlers, not to applications using keys issued by Wykop;
confirm this reading with the course lead or with Wykop.
"""

import random
import time
from collections.abc import Callable, Iterator
from typing import Any

import requests

from amc.youtube.api_client import CollectionError

API = "https://wykop.pl/api/v3"
PAGE_SIZE = 50  # maximum allowed by the API


class WykopClient:
    """Authenticated GET requests with 1-2 s pauses and growing waits after 429 or 5xx."""

    def __init__(
        self,
        key: str,
        secret: str,
        *,
        user_agent: str,
        delay: tuple[float, float] = (1.0, 2.0),
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._key, self._secret = key, secret
        self.delay = delay
        self.request_count = 0
        self._session = session if session is not None else requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._sleeper = sleeper
        self.login()

    def close(self) -> None:
        self._session.close()

    def login(self) -> None:
        response = self._session.post(
            API + "/auth", json={"data": {"key": self._key, "secret": self._secret}}, timeout=30
        )
        if response.status_code != 200:
            raise CollectionError(
                f"Wykop login failed (HTTP {response.status_code}); "
                "check WYKOP_KEY and WYKOP_SECRET."
            )
        self._session.headers["Authorization"] = "Bearer " + response.json()["data"]["token"]

    def get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        """Parsed JSON; an empty dict for HTTP 404. Logs in again once when the token expires."""
        relogged = False
        for attempt in range(7):
            self.request_count += 1
            try:
                response = self._session.get(API + path, params=params, timeout=30)
            except requests.RequestException:
                self._sleeper(10 * 2**attempt)
                continue
            self._sleeper(random.uniform(*self.delay))
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                return {}
            if response.status_code in (401, 403) and not relogged:
                self.login()
                relogged = True
            elif response.status_code == 429 or response.status_code >= 500:
                self._sleeper(min(10 * 2**attempt, 600))
            else:
                raise CollectionError(f"Wykop API returned HTTP {response.status_code} for {path}.")
        raise CollectionError(f"Too many failed attempts for {path}.")

    def pages(self, path: str, params: dict[str, Any] | None = None) -> Iterator[list[dict]]:
        """Items page by page until the last page."""
        page = 1
        while True:
            data = self.get(path, {**(params or {}), "page": page, "limit": PAGE_SIZE})
            items = data.get("data") or []
            yield items
            if not items or page * PAGE_SIZE >= (data.get("pagination") or {}).get("total", 0):
                return
            page += 1

    def entries(self, tag: str, year: int, month: int) -> Iterator[list[dict]]:
        """Microblog entries (not links) tagged `tag` in one month."""
        params = {"sort": "all", "type": "entry", "year": year, "month": month}
        return self.pages(f"/tags/{tag}/stream", params)

    def comments(self, entry_id: int) -> list[dict]:
        return [comment for page in self.pages(f"/entries/{entry_id}/comments") for comment in page]
