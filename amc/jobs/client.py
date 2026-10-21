"""Polite, cached access to advertisement pages."""

import os
import random
import time
from collections.abc import Callable
from pathlib import Path

import requests

from amc.youtube.api_client import CollectionError

BASE_URL = "https://nabory.kprm.gov.pl"
DEFAULT_USER_AGENT = "AMC-student-research/0.1"
RETRY_STATUSES = {429, 502, 503, 504}
# Pages open under any slug; older ads may need a different template suffix.
URL_TEMPLATES = (
    BASE_URL + "/a/b/c,{ad_id},v8",
    BASE_URL + "/a/b/c,{ad_id},v7",
    BASE_URL + "/a/b/c,{ad_id}",
)
AD_MARKER = "Ogłoszenie nr"


def user_agent() -> str:
    # Set KPRM_USER_AGENT or AMC_USER_AGENT to include contact details for the operator.
    return os.getenv("KPRM_USER_AGENT") or os.getenv("AMC_USER_AGENT") or DEFAULT_USER_AGENT


class KPRMClient:
    """Fetch advertisements by ID with a fixed delay, retries and an optional raw HTML cache."""

    def __init__(
        self,
        cache_dir: Path | None,
        *,
        delay: float = 2.0,
        jitter: float = 0.0,
        retries: int = 3,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.cache_dir = cache_dir
        self.delay = delay
        self.jitter = jitter
        self.retries = retries
        self.request_count = 0
        self._templates = list(URL_TEMPLATES)
        self._session = session if session is not None else requests.Session()
        self._session.headers["User-Agent"] = user_agent()
        self._sleeper = sleeper

    def close(self) -> None:
        self._session.close()

    def _get(self, url: str) -> requests.Response | None:
        """Response for status 200, None for 404 or 500; retries transient failures."""
        for attempt in range(self.retries + 1):
            pause = self.delay * (2**attempt if attempt else 1)
            self._sleeper(pause + random.uniform(0, self.jitter))
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
            return response
        raise CollectionError("Too many failed attempts.")

    def fetch_ad(self, ad_id: int) -> str | None:
        """Return page HTML, or None when the ID does not exist (HTTP 404 or 500)."""
        cached = self.cache_dir / f"{ad_id}.html" if self.cache_dir else None
        if cached and cached.exists():
            return cached.read_text(encoding="utf-8")
        response = self._get(URL_TEMPLATES[0].format(ad_id=ad_id))
        if response is None:
            return None
        if cached:
            cached.parent.mkdir(parents=True, exist_ok=True)
            cached.write_text(response.text, encoding="utf-8")
        return response.text

    def find_ad(self, ad_id: int) -> tuple[str, str] | None:
        """HTML and final URL of the first template that shows an advertisement.

        The template that worked last is tried first, so most IDs need one request.
        """
        for template in list(self._templates):
            response = self._get(template.format(ad_id=ad_id))
            if response is not None and AD_MARKER in response.text:
                self._templates.remove(template)
                self._templates.insert(0, template)
                return response.text, response.url
        return None
