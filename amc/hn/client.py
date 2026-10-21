"""Official Hacker News APIs only: HN Search (Algolia) and Firebase. No site pages are fetched."""

import random
import time
from collections.abc import Callable
from typing import Any

import requests

from amc.jobs.client import DEFAULT_USER_AGENT

ALGOLIA = "https://hn.algolia.com/api/v1"
FIREBASE = "https://hacker-news.firebaseio.com/v0"


class HNClient:
    """JSON requests with a short random delay and growing waits after 429 or 5xx."""

    def __init__(
        self,
        *,
        user_agent: str = DEFAULT_USER_AGENT,
        delay: tuple[float, float] = (0.5, 1.0),
        retries: int = 5,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.delay = delay
        self.retries = retries
        self.request_count = 0
        self._session = session if session is not None else requests.Session()
        self._session.headers["User-Agent"] = user_agent
        self._sleeper = sleeper

    def close(self) -> None:
        self._session.close()

    def get(self, url: str, params: dict[str, Any] | None = None) -> Any:
        """Parsed JSON, or None after repeated failures."""
        for attempt in range(self.retries):
            self.request_count += 1
            try:
                response = self._session.get(url, params=params, timeout=(5, 30))
            except requests.RequestException:
                self._sleeper(10 * (attempt + 1))
                continue
            self._sleeper(random.uniform(*self.delay))
            if response.status_code == 429 or response.status_code >= 500:
                self._sleeper(15 * 2**attempt)
                continue
            if response.status_code != 200:
                return None
            return response.json()
        return None

    def threads(self, start: int, end: int) -> list[dict[str, Any]]:
        """Stories of the whoishiring account created in [start, end) Unix time."""
        data = self.get(
            ALGOLIA + "/search_by_date",
            {
                "tags": "story,author_whoishiring",
                "hitsPerPage": 1000,
                "numericFilters": f"created_at_i>={start},created_at_i<{end}",
            },
        )
        if data is None:
            raise ConnectionError("HN Search did not return the thread list.")
        return data["hits"]

    def item(self, item_id: int) -> dict[str, Any] | None:
        return self.get(f"{FIREBASE}/item/{item_id}.json")

    def tree(self, item_id: int) -> dict[str, Any]:
        """Whole comment tree in one request; deleted and dead comments are absent."""
        return self.get(f"{ALGOLIA}/items/{item_id}") or {}
