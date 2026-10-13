"""Optional caption collection with language preference and request spacing."""

import random
import time
from collections.abc import Callable
from typing import Any

import requests
from youtube_transcript_api import (
    CouldNotRetrieveTranscript,
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    YouTubeRequestFailed,
    YouTubeTranscriptApi,
)

from amc.youtube.api_client import CollectionError, CollectionStopped
from amc.youtube.comment_extractor import clean_text
from amc.youtube.models import Transcript


class TranscriptHTTPSession(requests.Session):
    """Enforce timeouts and stop before the caption library wraps HTTP 403/429."""

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        kwargs.setdefault("timeout", (5, 30))
        response = super().request(method, url, **kwargs)
        if response.status_code in (403, 429):
            status = response.status_code
            response.close()
            raise CollectionStopped(f"Transcript HTTP {status}; collection stopped.")
        return response


class TranscriptFetcher:
    """Fetch Polish or English captions; spacing is not a guarantee against blocking."""

    def __init__(
        self,
        api: YouTubeTranscriptApi | None = None,
        *,
        sleeper: Callable[[float], None] = time.sleep,
        delay: Callable[[], float] | None = None,
    ) -> None:
        self._session = TranscriptHTTPSession() if api is None else None
        self._api = api if api is not None else YouTubeTranscriptApi(http_client=self._session)
        self._sleeper = sleeper
        self._delay = delay if delay is not None else lambda: random.uniform(0.5, 1.5)
        self._requested = False

    def close(self) -> None:
        """Close the session owned by this fetcher."""
        if self._session is not None:
            self._session.close()

    def fetch(self, video_id: str) -> Transcript:
        """Return joined captions, or None if disabled or unavailable in pl/en."""
        if self._requested:
            self._sleeper(self._delay())
        self._requested = True
        try:
            fetched = self._api.fetch(video_id, languages=["pl", "en"])
            return Transcript(video_id, clean_text(" ".join(snippet.text for snippet in fetched)))
        except (TranscriptsDisabled, NoTranscriptFound):
            return Transcript(video_id, None)
        except (RequestBlocked, IpBlocked):
            raise CollectionStopped(
                "YouTube blocked transcript requests; collection stopped."
            ) from None
        except requests.HTTPError as error:
            status = error.response.status_code if error.response is not None else None
            if status in (403, 429):
                raise CollectionStopped(f"Transcript HTTP {status}; collection stopped.") from None
            raise CollectionError("Transcript HTTP request failed; collection stopped.") from None
        except requests.RequestException:
            raise CollectionError("Transcript connection failed or timed out.") from None
        except YouTubeRequestFailed as error:
            for cause in (error.__cause__, error.__context__):
                if isinstance(cause, requests.HTTPError) and cause.response is not None:
                    if cause.response.status_code in (403, 429):
                        raise CollectionStopped(
                            "Transcript access or rate limit reached."
                        ) from None
            raise CollectionError("Transcript HTTP request failed; collection stopped.") from None
        except CouldNotRetrieveTranscript:
            return Transcript(video_id, None)
