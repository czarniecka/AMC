"""UTF-8 BOM CSV exports using allowlisted columns and atomic file replacement."""

import csv
import os
import tempfile
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from amc.youtube.models import Comment, Transcript, VideoMetadata

VIDEO_COLUMNS = (
    "video_id",
    "title",
    "channel_title",
    "published_at",
    "view_count",
    "comment_count",
)
COMMENT_COLUMNS = ("video_id", "comment_id", "text_clean", "like_count", "published_at")
TRANSCRIPT_COLUMNS = ("video_id", "transcript")
TEXT_COLUMNS = {"title", "channel_title", "text_clean", "transcript"}


def _spreadsheet_safe(
    value: object, column: str, text_columns: Iterable[str] = TEXT_COLUMNS
) -> object:
    """Neutralize formula-like free text when a CSV is opened in a spreadsheet."""
    if (
        column in text_columns
        and isinstance(value, str)
        and value.lstrip().startswith(("=", "+", "-", "@"))
    ):
        return "'" + value
    return value


def write_csv(
    path: Path,
    columns: tuple[str, ...],
    records: Iterable[Any],
    text_columns: Iterable[str] = TEXT_COLUMNS,
) -> None:
    """Write only the requested fields, with headers even when the collection is empty."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            newline="",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="raise")
            writer.writeheader()
            for record in records:
                row = asdict(record)
                writer.writerow(
                    {
                        column: _spreadsheet_safe(row[column], column, text_columns)
                        for column in columns
                    }
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def export_collection(
    output_dir: Path,
    videos: Iterable[VideoMetadata],
    comments: Iterable[Comment],
    transcripts: Iterable[Transcript],
) -> None:
    """Replace the three specified CSV exports; files are atomic individually."""
    write_csv(output_dir / "yt_videos_metadata.csv", VIDEO_COLUMNS, videos)
    write_csv(output_dir / "yt_comments_anonymized.csv", COMMENT_COLUMNS, comments)
    write_csv(output_dir / "yt_transcripts.csv", TRANSCRIPT_COLUMNS, transcripts)
