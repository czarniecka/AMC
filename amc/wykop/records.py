"""Rows for entries and comments with minimal personal data.

Usernames are replaced by SHA-256 of a secret salt and the username, so posts of one author can
be counted without knowing who it is. Avatars, gender, account colours and images are never
stored. E-mail addresses, phone numbers and @mentions are masked in the text.
"""

import hashlib
import re
from datetime import date

from amc.privacy import mask_contacts

COLUMNS = (
    "entry_id",
    "parent_id",
    "type",
    "tag",
    "created_at",
    "text",
    "tags",
    "upvotes",
    "comment_count",
    "author_hash",
    "url",
    "fetched_at",
)
ENTRY, COMMENT = "entry", "comment"

MENTION = re.compile(r"(?<![\w@])@[\w-]{2,}")


def scrub(text: str | None) -> str:
    # Contacts first, so that the @ of an e-mail address is not taken for a mention.
    return MENTION.sub("@[UZYTKOWNIK]", mask_contacts(text or ""))


class RowBuilder:
    def __init__(self, salt: str) -> None:
        self._salt = salt

    def author_hash(self, item: dict) -> str:
        nick = (item.get("author") or {}).get("username")
        return hashlib.sha256((self._salt + nick).encode()).hexdigest() if nick else ""

    def _row(self, item: dict, kind: str, tag: str, parent_id, url: str, count) -> dict:
        return {
            "entry_id": item["id"],
            "parent_id": parent_id,
            "type": kind,
            "tag": tag,
            # The API gives Polish local time without a zone: '2019-02-25 20:35:18'.
            "created_at": (item.get("created_at") or "").replace(" ", "T"),
            "text": scrub(item.get("content")),
            "tags": ",".join(item.get("tags") or []),
            "upvotes": (item.get("votes") or {}).get("up", ""),
            "comment_count": count,
            "author_hash": self.author_hash(item),
            "url": url,
            "fetched_at": date.today().isoformat(),
        }

    def entry(self, entry: dict, tag: str) -> dict:
        url = f"https://wykop.pl/wpis/{entry['id']}/{entry.get('slug') or ''}".rstrip("/")
        return self._row(entry, ENTRY, tag, "", url, (entry.get("comments") or {}).get("count", ""))

    def comment(self, comment: dict, entry_id, entry_url: str, tag: str) -> dict:
        return self._row(comment, COMMENT, tag, entry_id, f"{entry_url}#{comment['id']}", "")


def select_comments(comments: list[dict], min_upvotes: int | None, first: int) -> list[dict]:
    """Comments with text, oldest first. With `min_upvotes`, only those with more upvotes;
    when none qualifies, the first `first` comments."""
    comments = sorted(
        (c for c in comments if c.get("content")), key=lambda c: c.get("created_at") or ""
    )
    if min_upvotes is None:
        return comments
    popular = [c for c in comments if (c.get("votes") or {}).get("up", 0) > min_upvotes]
    return popular or comments[:first]
