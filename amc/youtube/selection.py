"""Load a reviewed video selection independently of application code."""

import json
import re
from pathlib import Path

from amc.youtube.comment_extractor import MAX_COMMENTS_PER_VIDEO


def load_selection(path: Path) -> tuple[tuple[str, ...], int]:
    """Validate IDs and pilot limits before any collection request is made."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ValueError("Cannot read video selection JSON.") from None
    if not isinstance(payload, dict):
        raise ValueError("Video selection must be a JSON object.")
    ids = payload.get("video_ids")
    limit = payload.get("max_comments", 1000)
    if (
        not isinstance(ids, list)
        or not 1 <= len(ids) <= 500
        or any(
            not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", value)
            for value in ids
        )
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("Provide 1–500 unique valid video IDs.")
    if type(limit) is not int or not 0 <= limit <= MAX_COMMENTS_PER_VIDEO:
        raise ValueError(f"max_comments must be an integer between 0 and {MAX_COMMENTS_PER_VIDEO}.")
    return tuple(ids), limit
