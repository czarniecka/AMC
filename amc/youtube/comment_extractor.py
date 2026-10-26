"""Collect top-level text without requesting author metadata or upstream comment IDs."""

import html
from collections.abc import Iterator
from uuid import uuid4

from amc.youtube.api_client import CollectionError, YouTubeAPIClient
from amc.youtube.models import Comment

COMMENT_FIELDS = (
    "nextPageToken,items(snippet/topLevelComment/snippet(textDisplay,likeCount,publishedAt))"
)
MAX_COMMENTS_PER_VIDEO = 5000


def clean_text(text: str) -> str:
    """Decode entities and normalize whitespace from API plain-text comments."""
    return " ".join(html.unescape(text).split())


def extract_comments(
    client: YouTubeAPIClient,
    video_id: str,
    *,
    max_comments: int = 1000,
    order: str = "relevance",
) -> Iterator[Comment]:
    """Yield a bounded set of top-level comments, preserving pages on failure."""
    if not 0 <= max_comments <= MAX_COMMENTS_PER_VIDEO:
        raise ValueError(f"max_comments must be between 0 and {MAX_COMMENTS_PER_VIDEO}")
    if order not in {"relevance", "time"}:
        raise ValueError("Comment order must be relevance or time")
    count = 0
    page_token = ""
    used_tokens: set[str] = set()
    while count < max_comments:
        params: dict[str, str | int] = {
            "part": "snippet",
            "videoId": video_id,
            "maxResults": min(100, max_comments - count),
            "order": order,
            "textFormat": "plainText",
            "fields": COMMENT_FIELDS,
        }
        if page_token:
            params["pageToken"] = page_token
        response = client.get("commentThreads", params)
        for item in response.get("items", []):
            if count >= max_comments:
                break
            snippet = item["snippet"]["topLevelComment"]["snippet"]
            yield Comment(
                video_id=video_id,
                comment_id=str(uuid4()),
                text_clean=clean_text(snippet["textDisplay"]),
                like_count=int(snippet.get("likeCount", 0)),
                published_at=snippet["publishedAt"],
            )
            count += 1
        next_token = response.get("nextPageToken")
        if not next_token:
            break
        if next_token in used_tokens:
            raise CollectionError("YouTube returned a repeated comment page token.")
        used_tokens.add(next_token)
        page_token = next_token
