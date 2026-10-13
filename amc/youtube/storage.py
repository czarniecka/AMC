"""Authoritative CSV history with one-time read-only migration from SQLite."""

import csv
import hashlib
import json
import os
import shutil
import sqlite3
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from amc.youtube.api_client import CollectionError
from amc.youtube.exporter import COMMENT_COLUMNS, TRANSCRIPT_COLUMNS, VIDEO_COLUMNS, write_csv
from amc.youtube.models import Comment, Transcript, VideoMetadata


@dataclass
class CommentState:
    video_id: str
    completed: int
    sample_limit: int
    comment_order: str


def comment_fingerprint(comment: Comment) -> str:
    """Deduplicate without retaining source author or comment identifiers."""
    return hashlib.sha256(
        json.dumps(
            [comment.video_id, comment.text_clean, comment.published_at], ensure_ascii=False
        ).encode()
    ).hexdigest()


class CollectionStore:
    """CSV files are authoritative; completed samples are tracked in a fourth CSV."""

    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        self.lock = output_dir / ".collection.lock"
        try:
            descriptor = os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise CollectionError(
                "Another collection is active. "
                "Remove .collection.lock only after confirming it stopped."
            ) from None
        os.close(descriptor)
        self._videos = {}
        self._comments = {}
        self._transcripts = {}
        self._state = {}
        try:
            state_path = output_dir / "yt_collection_state.csv"
            if not state_path.exists():
                self._initialize_history()
            self._load()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        self.lock.unlink(missing_ok=True)

    @staticmethod
    def _read(path: Path) -> list[dict[str, str]]:
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream)
            schemas = {
                "yt_videos_metadata.csv": VIDEO_COLUMNS,
                "yt_comments_anonymized.csv": COMMENT_COLUMNS,
                "yt_transcripts.csv": TRANSCRIPT_COLUMNS,
                "yt_collection_state.csv": (
                    "video_id",
                    "completed",
                    "sample_limit",
                    "comment_order",
                ),
            }
            if tuple(reader.fieldnames or ()) != schemas[path.name]:
                raise ValueError("Unexpected CSV headers")
            rows = list(reader)
            if any(None in row or any(value is None for value in row.values()) for row in rows):
                raise ValueError("Incomplete CSV row")
            return rows

    @staticmethod
    def _text(value: str) -> str:
        # Decode the spreadsheet-safety prefix introduced by our exporter.
        return (
            value[1:]
            if value.startswith("'") and value[1:].lstrip().startswith(("=", "+", "-", "@"))
            else value
        )

    def _load(self) -> None:
        self._videos.clear()
        self._comments.clear()
        self._transcripts.clear()
        self._state.clear()
        try:
            if (self.output_dir / "yt_collection_state.csv").exists():
                states = self._read(self.output_dir / "yt_collection_state.csv")
                if states and (
                    not (self.output_dir / "yt_videos_metadata.csv").exists()
                    or not (self.output_dir / "yt_comments_anonymized.csv").exists()
                ):
                    raise ValueError("Missing files for an existing collection")
            for row in self._read(self.output_dir / "yt_videos_metadata.csv"):
                video = VideoMetadata(
                    row["video_id"],
                    self._text(row["title"]),
                    self._text(row["channel_title"]),
                    row["published_at"],
                    int(row["view_count"]) if row["view_count"] else None,
                    int(row["comment_count"]) if row["comment_count"] else None,
                )
                if video.video_id in self._videos:
                    raise ValueError("Duplicate video ID")
                self._videos[video.video_id] = video
            for row in self._read(self.output_dir / "yt_comments_anonymized.csv"):
                comment = Comment(
                    row["video_id"],
                    row["comment_id"],
                    self._text(row["text_clean"]),
                    int(row["like_count"]),
                    row["published_at"],
                )
                if comment.video_id not in self._videos:
                    raise ValueError("Unknown video")
                self._comments.setdefault(comment_fingerprint(comment), comment)
            for row in self._read(self.output_dir / "yt_transcripts.csv"):
                self._transcripts[row["video_id"]] = Transcript(
                    row["video_id"], self._text(row["transcript"]) or None
                )
            for row in self._read(self.output_dir / "yt_collection_state.csv"):
                if (
                    row["video_id"] not in self._videos
                    or row["video_id"] in self._state
                    or row["completed"] not in {"0", "1"}
                    or not 0 <= int(row["sample_limit"]) <= 500
                    or row["comment_order"] not in {"time", "relevance"}
                ):
                    raise ValueError("Invalid collection state")
                self._state[row["video_id"]] = CommentState(
                    row["video_id"],
                    int(row["completed"]),
                    int(row["sample_limit"]),
                    row["comment_order"],
                )
        except (KeyError, ValueError, csv.Error):
            raise CollectionError(
                "Invalid collection CSV. Check column headers and values; originals are retained."
            ) from None

    def _initialize_history(self) -> None:
        existing = list(self.output_dir.glob("*.csv"))
        database = self.output_dir / "yt_collection.sqlite3"
        if existing or database.exists():
            backup = self.output_dir / "backups" / ("csv-migration-" + uuid4().hex[:12])
            backup.mkdir(parents=True)
            for path in existing + ([database] if database.exists() else []):
                shutil.copy2(path, backup / path.name)
        if database.exists():
            # Only migration uses sqlite3; normal collection never opens a database.
            with closing(
                sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
            ) as connection:
                videos = [VideoMetadata(*row) for row in connection.execute("SELECT * FROM videos")]
                comments = [
                    Comment(*row)
                    for row in connection.execute(
                        "SELECT video_id,comment_id,text_clean,like_count,published_at "
                        "FROM comments ORDER BY rowid"
                    )
                ]
                transcripts = [
                    Transcript(*row)
                    for row in connection.execute("SELECT video_id,transcript FROM transcripts")
                ]
                states = [
                    CommentState(*row) for row in connection.execute("SELECT * FROM comment_state")
                ]
            write_csv(self.output_dir / "yt_videos_metadata.csv", VIDEO_COLUMNS, videos)
            write_csv(self.output_dir / "yt_comments_anonymized.csv", COMMENT_COLUMNS, comments)
            write_csv(self.output_dir / "yt_transcripts.csv", TRANSCRIPT_COLUMNS, transcripts)
            for state in states:
                self._state[state.video_id] = state
        else:
            self._load()
            counts = {}
            for comment in self._comments.values():
                counts[comment.video_id] = counts.get(comment.video_id, 0) + 1
            for video_id, count in counts.items():
                self._state[video_id] = CommentState(video_id, 1, count, "relevance")
        self._save_state()
        if database.exists():
            database.rename(backup / "retired-yt_collection.sqlite3")

    def _save_state(self) -> None:
        write_csv(
            self.output_dir / "yt_collection_state.csv",
            ("video_id", "completed", "sample_limit", "comment_order"),
            self._state.values(),
        )

    def save_video(self, video: VideoMetadata) -> None:
        if video.video_id not in self._videos:
            self._videos[video.video_id] = video
            write_csv(self.output_dir / "yt_videos_metadata.csv", VIDEO_COLUMNS, self.videos())

    def save_comment(self, comment: Comment) -> bool:
        key = comment_fingerprint(comment)
        if key in self._comments:
            return False
        self._comments[key] = comment
        write_csv(self.output_dir / "yt_comments_anonymized.csv", COMMENT_COLUMNS, self.comments())
        return True

    def comments_completed(self, video_id: str) -> bool:
        return bool(video_id in self._state and self._state[video_id].completed)

    def mark_comments(self, video_id: str, *, completed: bool, limit: int, order: str) -> None:
        self._state[video_id] = CommentState(video_id, int(completed), limit, order)
        self._save_state()

    def save_transcript(self, transcript: Transcript) -> None:
        if transcript.transcript or not self.has_transcript(transcript.video_id):
            self._transcripts[transcript.video_id] = transcript
            write_csv(
                self.output_dir / "yt_transcripts.csv", TRANSCRIPT_COLUMNS, self.transcripts()
            )

    def has_transcript(self, video_id: str) -> bool:
        return bool(video_id in self._transcripts and self._transcripts[video_id].transcript)

    def videos(self) -> list[VideoMetadata]:
        return sorted(self._videos.values(), key=lambda video: video.video_id)

    def comments(self) -> Iterable[Comment]:
        return iter(self._comments.values())

    def transcripts(self) -> list[Transcript]:
        return [
            self._transcripts.get(video.video_id, Transcript(video.video_id, None))
            for video in self.videos()
        ]
