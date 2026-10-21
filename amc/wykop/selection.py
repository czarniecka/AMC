"""Load the reviewed Wykop collection settings independently of application code."""

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Selection:
    tags: tuple[str, ...]
    start: date
    min_upvotes: int | None  # None keeps every comment
    first: int


def load_selection(path: Path) -> Selection:
    """Validate tags, start date and the comment rule before any request is made."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        raise ValueError("Cannot read Wykop collection JSON.") from None
    if not isinstance(payload, dict):
        raise ValueError("Wykop collection settings must be a JSON object.")
    tags = payload.get("tags")
    if (
        not isinstance(tags, list)
        or not tags
        or any(not isinstance(tag, str) or not re.fullmatch(r"[a-z0-9]+", tag) for tag in tags)
        or len(set(tags)) != len(tags)
    ):
        raise ValueError("Provide unique lowercase tags without '#'.")
    try:
        start = date.fromisoformat(payload.get("start", ""))
    except (TypeError, ValueError):
        raise ValueError("start must be a YYYY-MM-DD date.") from None
    comments = payload.get("comments", {})
    if not isinstance(comments, dict):
        raise ValueError("comments must be a JSON object.")
    min_upvotes, first = comments.get("min_upvotes"), comments.get("first", 5)
    if min_upvotes is not None and (type(min_upvotes) is not int or min_upvotes < 0):
        raise ValueError("comments.min_upvotes must be a non-negative integer or null.")
    if type(first) is not int or not 1 <= first <= 50:
        raise ValueError("comments.first must be an integer between 1 and 50.")
    return Selection(tuple(tags), start, min_upvotes, first)
