"""Polite, cached access to advertisement pages."""

import os
import time
from collections.abc import Callable
from pathlib import Path

import requests

from amc.youtube.api_client import CollectionError

BASE_URL = "https://nabory.kprm.gov.pl"
DEFAULT_USER_AGENT = "AMC-student-research/0.1"
RETRY_STATUSES = {429, 502, 503, 504}


class KPRMClient:
    """Fetch advertisements by ID with a fixed delay, retries and a raw HTML cache."""

    def __init__(
        self,
        cache_dir: Path,
        *,
        delay: float = 2.0,
        retries: int = 3,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cache_dir = cache_dir
        self.delay = delay
        self.retries = retries
        self.request_count = 0
        self._session = session if session is not None else requests.Session()
        # Set KPRM_USER_AGENT to include contact details so the operator can reach you.
        self._session.headers["User-Agent"] = os.getenv("KPRM_USER_AGENT", DEFAULT_USER_AGENT)
        self._sleeper = sleeper

    def close(self) -> None:
        self._session.close()

    def fetch_ad(self, ad_id: int) -> str | None:
        """Return page HTML, or None when the ID does not exist (HTTP 404 or 500)."""
        cached = self.cache_dir / f"{ad_id}.html"
        if cached.exists():
            return cached.read_text(encoding="utf-8")
        url = f"{BASE_URL}/a/b/c,{ad_id},v8"
        for attempt in range(self.retries + 1):
            self._sleeper(self.delay * (2**attempt if attempt else 1))
            self.request_count += 1
            try:
                response = self._session.get(url, timeout=(5, 30))
            except requests.RequestException:
                if attempt == self.retries:
                    raise CollectionError("The server is unreachable; try again later.") from None
                continue
            if response.status_code in (404, 500):
                return None
            if response.status_code in RETRY_STATUSES and attempt < self.retries:
                continue
            if response.status_code != 200:
                raise CollectionError(f"Unexpected HTTP status {response.status_code}.")
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cached.write_text(response.text, encoding="utf-8")
            return response.text
        raise CollectionError("Too many failed attempts.")
