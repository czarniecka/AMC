"""Bounded YouTube Data API requests without logging URLs or API credentials."""

import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


class CollectionError(Exception):
    """A safe, human-readable failure suitable for console output."""


class CollectionStopped(CollectionError):
    """Stop all collection after a quota, access, rate, or local budget limit."""


class YouTubeAPIClient:
    """Issue allowlisted API calls with timeouts and a per-run request budget."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(
        self,
        api_key: str | None = None,
        *,
        max_requests: int = 200,
        session: requests.Session | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if api_key is None:
            load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
        self._api_key = api_key if api_key is not None else os.getenv("YOUTUBE_API_KEY", "")
        if not self._api_key.strip():
            raise CollectionError(
                "Set YOUTUBE_API_KEY in .env or the environment before collecting."
            )
        if max_requests < 1:
            raise ValueError("max_requests must be positive")
        self.max_requests = max_requests
        self.request_count = 0
        self._session = session if session is not None else requests.Session()
        self._sleeper = sleeper

    def close(self) -> None:
        """Release the HTTP connection pool."""
        self._session.close()

    def get(self, resource: str, params: dict[str, str | int]) -> dict[str, Any]:
        """Retry transient server failures, but never retry HTTP 403 or 429."""
        if resource not in {"search", "videos", "commentThreads"}:
            raise ValueError("Unsupported API resource")
        if not params.get("fields"):
            raise ValueError("An explicit response fields allowlist is required")
        for attempt in range(3):
            if self.request_count >= self.max_requests:
                raise CollectionStopped("Local API request budget reached; collection stopped.")
            self.request_count += 1
            try:
                response = self._session.get(
                    f"{self.BASE_URL}/{resource}",
                    params={**params, "key": self._api_key},
                    timeout=(5, 30),
                )
            except requests.RequestException:
                raise CollectionError("YouTube API connection failed or timed out.") from None
            try:
                status = response.status_code
                if status in (403, 429):
                    if status == 429:
                        raise CollectionStopped("YouTube HTTP 429: rate limit reached; stopped.")
                    reason = self._error_reason(response)
                    explanations = {
                        "quotaExceeded": "API quota exceeded",
                        "dailyLimitExceeded": "daily API limit exceeded",
                        "rateLimitExceeded": "API rate limit exceeded",
                        "commentsDisabled": "comments are disabled for a selected video",
                        "keyInvalid": "API key is invalid",
                    }
                    explanation = explanations.get(reason, "access denied; check key and quota")
                    raise CollectionStopped(f"YouTube HTTP 403: {explanation}; stopped.")
                if 500 <= status < 600 and attempt < 2:
                    self._sleeper(2**attempt)
                    continue
                if status != 200:
                    raise CollectionError(
                        f"YouTube API returned HTTP {status}; collection stopped."
                    )
                try:
                    payload = response.json()
                except ValueError:
                    raise CollectionError("YouTube API returned invalid JSON.") from None
                if not isinstance(payload, dict):
                    raise CollectionError("YouTube API returned an unexpected response shape.")
                return payload
            finally:
                response.close()
        raise CollectionError("YouTube API server failure.")

    @staticmethod
    def _error_reason(response: requests.Response) -> str:
        """Inspect only the reason code; never print the raw error or request URL."""
        try:
            return str(response.json()["error"]["errors"][0]["reason"])
        except (ValueError, KeyError, IndexError, TypeError):
            return ""
