"""Typed export records and bilingual search defaults."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """A search phrase and a language relevance hint, not a strict language filter."""

    text: str
    language: str


DEFAULT_QUERIES = (
    SearchQuery("sztuczna inteligencja rynek pracy", "pl"),
    SearchQuery("wymagania kompetencyjne ChatGPT", "pl"),
    SearchQuery("AI kompetencje przyszłości praca", "pl"),
    SearchQuery("AI job market skills", "en"),
    SearchQuery("ChatGPT changing job requirements", "en"),
    SearchQuery("generative AI workforce upskilling", "en"),
)


@dataclass(frozen=True, slots=True)
class VideoMetadata:
    """Selected video metadata; missing statistics remain unknown."""

    video_id: str
    title: str
    channel_title: str
    published_at: str
    view_count: int | None
    comment_count: int | None


@dataclass(frozen=True, slots=True)
class Comment:
    """A top-level comment with a fresh UUID and no author metadata."""

    video_id: str
    comment_id: str
    text_clean: str
    like_count: int
    published_at: str


@dataclass(frozen=True, slots=True)
class Transcript:
    """Joined caption text; None represents unavailable or unrequested captions."""

    video_id: str
    transcript: str | None
