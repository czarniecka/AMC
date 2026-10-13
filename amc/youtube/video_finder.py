"""Find bilingual candidates and rank their retrieved statistics by comment count."""

import html
from collections.abc import Iterator, Sequence
from datetime import datetime, timezone

from amc.youtube.api_client import CollectionError, YouTubeAPIClient
from amc.youtube.models import SearchQuery, VideoMetadata

SEARCH_FIELDS = "nextPageToken,items(id/videoId)"
VIDEO_FIELDS = (
    "items(id,snippet(title,channelTitle,publishedAt),statistics(viewCount,commentCount))"
)


def parse_timestamp(value: str) -> datetime:
    """Require a timezone-aware ISO timestamp for publication comparisons."""
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError("published_after must be an ISO timestamp with a timezone") from None
    if result.utcoffset() is None:
        raise ValueError("published_after must include a timezone")
    return result


def _optional_count(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except ValueError:
        raise CollectionError("YouTube returned a non-numeric video statistic.") from None


def iter_video_metadata(
    client: YouTubeAPIClient,
    queries: Sequence[SearchQuery],
    *,
    published_after: str = "2023-01-01T00:00:00Z",
    candidates_per_query: int = 50,
    exclude_video_ids: set[str] | None = None,
) -> Iterator[VideoMetadata]:
    """Yield deduplicated metadata in batches; use local ranking, not an invalid API order."""
    cutoff = parse_timestamp(published_after)
    api_cutoff = cutoff.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if not 1 <= candidates_per_query <= 500:
        raise ValueError("candidates_per_query must be between 1 and 500")
    seen_ids: set[str] = set(exclude_video_ids or ())
    for query in queries:
        if not query.text.strip() or query.language not in {"pl", "en"}:
            raise ValueError("Each query needs a non-empty phrase and language pl or en")
        page_token = ""
        used_tokens: set[str] = set()
        fetched = 0
        while fetched < candidates_per_query:
            params: dict[str, str | int] = {
                "part": "snippet",
                "type": "video",
                "q": query.text,
                "publishedAfter": api_cutoff,
                "relevanceLanguage": query.language,
                "order": "relevance",
                "maxResults": min(50, candidates_per_query - fetched),
                "fields": SEARCH_FIELDS,
            }
            if page_token:
                params["pageToken"] = page_token
            response = client.get("search", params)
            items = response.get("items", [])
            fetched += len(items)
            ids = []
            for item in items:
                video_id = item.get("id", {}).get("videoId")
                if video_id and video_id not in seen_ids:
                    seen_ids.add(video_id)
                    ids.append(video_id)
            if ids:
                metadata = client.get(
                    "videos",
                    {"part": "snippet,statistics", "id": ",".join(ids), "fields": VIDEO_FIELDS},
                )
                for item in metadata.get("items", []):
                    snippet = item["snippet"]
                    if parse_timestamp(snippet["publishedAt"]) <= cutoff:
                        continue
                    statistics = item.get("statistics", {})
                    yield VideoMetadata(
                        video_id=item["id"],
                        title=html.unescape(snippet["title"]),
                        channel_title=html.unescape(snippet["channelTitle"]),
                        published_at=snippet["publishedAt"],
                        view_count=_optional_count(statistics.get("viewCount")),
                        comment_count=_optional_count(statistics.get("commentCount")),
                    )
            next_token = response.get("nextPageToken")
            if not next_token:
                break
            if next_token in used_tokens:
                raise CollectionError("YouTube returned a repeated search page token.")
            used_tokens.add(next_token)
            page_token = next_token


def fetch_video_ids(client: YouTubeAPIClient, video_ids: Sequence[str]) -> Iterator[VideoMetadata]:
    """Fetch approved metadata directly by ID, without search or ranking."""
    for offset in range(0, len(video_ids), 50):
        batch = video_ids[offset : offset + 50]
        response = client.get(
            "videos", {"part": "snippet,statistics", "id": ",".join(batch), "fields": VIDEO_FIELDS}
        )
        found = set()
        for item in response.get("items", []):
            found.add(item["id"])
            snippet = item["snippet"]
            statistics = item.get("statistics", {})
            yield VideoMetadata(
                item["id"],
                html.unescape(snippet["title"]),
                html.unescape(snippet["channelTitle"]),
                snippet["publishedAt"],
                _optional_count(statistics.get("viewCount")),
                _optional_count(statistics.get("commentCount")),
            )
        if found != set(batch):
            raise CollectionError("Some approved videos are unavailable; check the selected IDs.")


def rank_videos(videos: Sequence[VideoMetadata], limit: int) -> list[VideoMetadata]:
    """Rank the retrieved candidate pool by comments, with unknown counts last."""
    if limit < 1:
        raise ValueError("Video limit must be positive")
    return sorted(
        videos,
        key=lambda video: (
            -(video.comment_count if video.comment_count is not None else -1),
            video.video_id,
        ),
    )[:limit]


def find_videos(
    client: YouTubeAPIClient,
    queries: Sequence[SearchQuery],
    *,
    max_videos: int = 20,
    published_after: str = "2023-01-01T00:00:00Z",
    candidates_per_query: int = 50,
) -> list[VideoMetadata]:
    """Return the requested metadata table as typed records sorted by comment count."""
    return rank_videos(
        list(
            iter_video_metadata(
                client,
                queries,
                published_after=published_after,
                candidates_per_query=candidates_per_query,
            )
        ),
        max_videos,
    )
