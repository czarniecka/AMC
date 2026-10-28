"""Coordinate bounded collection and preserve completed records on an API stop."""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from amc.youtube.api_client import CollectionError, YouTubeAPIClient
from amc.youtube.comment_extractor import MAX_COMMENTS_PER_VIDEO, extract_comments
from amc.youtube.exporter import export_collection
from amc.youtube.models import DEFAULT_QUERIES, Comment, SearchQuery, Transcript, VideoMetadata
from amc.youtube.storage import CollectionStore
from amc.youtube.transcript_fetcher import TranscriptFetcher
from amc.youtube.video_finder import (
    fetch_video_ids,
    iter_video_metadata,
    parse_timestamp,
    rank_videos,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CollectorConfig:
    """Bounded collection settings; captions are opt-in."""

    queries: tuple[SearchQuery, ...] = DEFAULT_QUERIES
    published_after: str = "2023-01-01T00:00:00Z"
    candidates_per_query: int = 50
    max_videos: int = 20
    max_comments: int = 1000
    include_transcripts: bool = False
    output_dir: Path = Path("data/youtube")
    refresh_comments: bool = False
    comment_order: str = "relevance"
    discover_only: bool = False
    video_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        parse_timestamp(self.published_after)
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{11}", value) for value in self.video_ids):
            raise ValueError("Each video ID must contain 11 YouTube ID characters")
        if self.video_ids and self.discover_only:
            raise ValueError("Explicit video IDs cannot be combined with discovery-only mode")
        if len(self.video_ids) > self.max_videos:
            raise ValueError("max_videos must cover every explicitly selected video")
        if not self.queries or any(
            not query.text.strip() or query.language not in {"pl", "en"} for query in self.queries
        ):
            raise ValueError("Provide at least one non-empty pl/en search query")
        if not 1 <= self.candidates_per_query <= 500:
            raise ValueError("candidates_per_query must be between 1 and 500")
        if not 1 <= self.max_videos <= 500:
            raise ValueError("max_videos must be between 1 and 500")
        if not 0 <= self.max_comments <= MAX_COMMENTS_PER_VIDEO:
            raise ValueError(f"max_comments must be between 0 and {MAX_COMMENTS_PER_VIDEO}")
        if self.comment_order not in {"relevance", "time"}:
            raise ValueError("comment_order must be relevance or time")


@dataclass(slots=True)
class CollectionResult:
    """Exportable records and an explicit indicator of an interrupted run."""

    videos: list[VideoMetadata] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    transcripts: list[Transcript] = field(default_factory=list)
    stopped_reason: str | None = None
    total_videos: int = 0
    total_comments: int = 0


class YouTubeDataCollector:
    """Collect metadata, top-level comments, and optional captions into CSV files."""

    def __init__(
        self,
        client: YouTubeAPIClient,
        config: CollectorConfig | None = None,
        *,
        transcript_fetcher: TranscriptFetcher | None = None,
    ) -> None:
        self.client = client
        self.config = config if config is not None else CollectorConfig()
        self._transcript_fetcher = transcript_fetcher

    def collect(self) -> CollectionResult:
        """Persist new records, skip completed samples, and export cumulative CSV files."""
        result = CollectionResult()
        store = CollectionStore(self.config.output_dir)
        existing = store.videos()
        if self.config.video_ids:
            by_id = {video.video_id: video for video in existing}
        candidates = [
            video
            for video in existing
            if self.config.refresh_comments
            or not store.comments_completed(video.video_id)
            or (self.config.include_transcripts and not store.has_transcript(video.video_id))
        ]
        if self.config.video_ids:
            candidates = [
                by_id[value] for value in dict.fromkeys(self.config.video_ids) if value in by_id
            ]
        fetched_transcripts: dict[str, Transcript] = {}
        try:
            if self.config.video_ids:
                missing = [
                    value for value in dict.fromkeys(self.config.video_ids) if value not in by_id
                ]
                for video in fetch_video_ids(self.client, missing):
                    if parse_timestamp(video.published_at) <= parse_timestamp(
                        self.config.published_after
                    ):
                        raise CollectionError(
                            "An approved video is at or before the publication cutoff."
                        )
                    store.save_video(video)
                    by_id[video.video_id] = video
                    candidates.append(video)
                candidates = [by_id[value] for value in dict.fromkeys(self.config.video_ids)]
            for video in iter_video_metadata(
                self.client,
                () if self.config.video_ids else self.config.queries,
                published_after=self.config.published_after,
                candidates_per_query=self.config.candidates_per_query,
                exclude_video_ids={video.video_id for video in existing},
            ):
                candidates.append(video)
                if self.config.discover_only:
                    store.save_video(video)
            result.videos = (
                candidates
                if self.config.discover_only or self.config.video_ids
                else rank_videos(candidates, self.config.max_videos)
            )
            for video in () if self.config.discover_only else result.videos:
                store.save_video(video)
                if self.config.max_comments and (
                    self.config.refresh_comments or not store.comments_completed(video.video_id)
                ):
                    store.mark_comments(
                        video.video_id,
                        completed=False,
                        limit=self.config.max_comments,
                        order=self.config.comment_order,
                    )
                    pending: list[Comment] = []
                    try:
                        for comment in extract_comments(
                            self.client,
                            video.video_id,
                            max_comments=self.config.max_comments,
                            order=self.config.comment_order,
                        ):
                            pending.append(comment)
                            if len(pending) >= 100:
                                result.comments.extend(store.save_comments(pending))
                                pending.clear()
                    finally:
                        if pending:
                            result.comments.extend(store.save_comments(pending))
                    store.mark_comments(
                        video.video_id,
                        completed=True,
                        limit=self.config.max_comments,
                        order=self.config.comment_order,
                    )
                if self.config.include_transcripts and not store.has_transcript(video.video_id):
                    if self._transcript_fetcher is None:
                        self._transcript_fetcher = TranscriptFetcher()
                    fetched_transcripts[video.video_id] = self._transcript_fetcher.fetch(
                        video.video_id
                    )
                    store.save_transcript(fetched_transcripts[video.video_id])
        except CollectionError as error:
            result.stopped_reason = str(error)
            logger.error("%s Completed records will be exported; outputs are partial.", error)
        finally:
            try:
                if self._transcript_fetcher is not None:
                    self._transcript_fetcher.close()
                if not result.videos:
                    result.videos = (
                        candidates
                        if self.config.discover_only or self.config.video_ids
                        else rank_videos(candidates, self.config.max_videos)
                    )
                for video in result.videos:
                    store.save_video(video)
                result.transcripts = [
                    fetched_transcripts.get(video.video_id, Transcript(video.video_id, None))
                    for video in result.videos
                ]
                result.total_videos = len(store.videos())
                result.total_comments = sum(1 for _ in store.comments())
                export_collection(
                    self.config.output_dir,
                    store.videos(),
                    store.comments(),
                    store.transcripts(),
                )
            finally:
                store.close()
        return result
