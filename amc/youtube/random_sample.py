"""Resumable, seeded search sample kept separate from the reviewed YouTube collection."""

import hashlib
import html
import json
import os
import random
import sqlite3
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from langdetect import DetectorFactory, LangDetectException, detect_langs

from amc.privacy import mask_contacts
from amc.youtube.api_client import CollectionError, YouTubeAPIClient
from amc.youtube.comment_extractor import clean_text

PERIODS = {
    "pre_chatgpt": ("2019-01-01T00:00:00Z", "2022-11-30T00:00:00Z"),
    "post_chatgpt": ("2022-11-30T00:00:00Z", "2027-01-01T00:00:00Z"),
}
SEARCH_FIELDS = "items(id/videoId)"
VIDEO_FIELDS = (
    "items(id,snippet(title,channelTitle,publishedAt,defaultAudioLanguage,"
    "defaultLanguage),statistics(viewCount,commentCount))"
)
COMMENT_FIELDS = (
    "nextPageToken,items(id,snippet/topLevelComment/snippet(textDisplay,likeCount,publishedAt))"
)
DetectorFactory.seed = 0


def period_of(timestamp: str) -> str:
    """Group a published comment by the UTC calendar date of ChatGPT's launch."""
    return "pre_chatgpt" if timestamp < PERIODS["pre_chatgpt"][1] else "post_chatgpt"


def is_english(text: str) -> bool:
    """Conservatively retain only comments identified as English."""
    try:
        return any(item.lang == "en" and item.prob >= 0.90 for item in detect_langs(text))
    except LangDetectException:
        return False


def vocabulary(path: Path) -> tuple[str, ...]:
    words = tuple(
        line.strip().lower()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if (
        len(words) < 2
        or len(set(words)) != len(words)
        or any(not all(part.isalpha() for part in w.split()) for w in words)
    ):
        raise ValueError("Vocabulary must contain unique alphabetic words or phrases")
    return words


def derived_seed(base: int, *parts: object) -> int:
    payload = json.dumps([base, *parts], separators=(",", ":"), ensure_ascii=True)
    return int.from_bytes(hashlib.sha256(payload.encode()).digest()[:8], "big")


def query_for(words: tuple[str, ...], seed: int, period: str, index: int) -> tuple[str, str, str]:
    """Visit every word/quarter pair once in a seeded order."""
    period_start, period_end = PERIODS[period]
    first_year = int(period_start[:4])
    last_year = int(period_end[:4])
    queries = []
    for year in range(first_year, last_year + 1):
        for month in (1, 4, 7, 10):
            next_year, next_month = (year + 1, 1) if month == 10 else (year, month + 3)
            start = max(period_start, f"{year}-{month:02d}-01T00:00:00Z")
            end = min(period_end, f"{next_year}-{next_month:02d}-01T00:00:00Z")
            if start >= end:
                continue
            for word in words:
                queries.append((word, start, end))
    random.Random(derived_seed(seed, "query-order", period)).shuffle(queries)
    if index >= len(queries):
        raise CollectionError("All vocabulary/quarter search pairs are exhausted")
    return queries[index]


@contextmanager
def locked(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = path.with_suffix(path.suffix + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise CollectionError(f"Collection is locked: {lock}") from None
    os.close(descriptor)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


class SampleStore:
    def __init__(self, path: Path, config: dict) -> None:
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS searches (
                period TEXT NOT NULL, query_index INTEGER NOT NULL, word TEXT NOT NULL,
                window_start TEXT NOT NULL, window_end TEXT NOT NULL,
                ids_json TEXT NOT NULL, selected_ids_json TEXT NOT NULL,
                expanded INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(period, query_index));
            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY, period TEXT NOT NULL, query_index INTEGER NOT NULL,
                selection_rank INTEGER NOT NULL, title TEXT NOT NULL, channel_title TEXT NOT NULL,
                published_at TEXT NOT NULL, view_count INTEGER NOT NULL,
                comment_count INTEGER NOT NULL, language TEXT NOT NULL,
                page_token TEXT NOT NULL DEFAULT '', pages_done INTEGER NOT NULL DEFAULT 0,
                done INTEGER NOT NULL DEFAULT 0,
                rejected_short INTEGER NOT NULL DEFAULT 0,
                rejected_language INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT PRIMARY KEY, video_id TEXT NOT NULL,
                video_period TEXT NOT NULL, comment_period TEXT NOT NULL,
                text_clean TEXT NOT NULL, like_count INTEGER NOT NULL,
                published_at TEXT NOT NULL, fetched_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS page_tokens (
                video_id TEXT NOT NULL, token TEXT NOT NULL,
                PRIMARY KEY(video_id, token));
            CREATE INDEX IF NOT EXISTS comments_period ON comments(comment_period);
        """)
        saved = self.db.execute("SELECT value FROM config WHERE key='protocol'").fetchone()
        serialized = json.dumps(config, sort_keys=True, separators=(",", ":"))
        if saved and saved[0] != serialized:
            self.db.close()
            raise ValueError("Sampling settings changed; use a new database or original settings")
        if not saved:
            with self.db:
                self.db.execute("INSERT INTO config VALUES ('protocol', ?)", (serialized,))

    def close(self) -> None:
        self.db.close()

    def count(self, period: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM comments WHERE comment_period=?", (period,)
        ).fetchone()[0]

    def unexpanded(self, period: str):
        return self.db.execute(
            "SELECT * FROM searches WHERE period=? AND expanded=0 ORDER BY query_index LIMIT 1",
            (period,),
        ).fetchone()

    def next_index(self, period: str) -> int:
        return self.db.execute(
            "SELECT COUNT(*) FROM searches WHERE period=?", (period,)
        ).fetchone()[0]

    def pending_video(self, period: str):
        return self.db.execute(
            "SELECT * FROM videos WHERE period=? AND done=0 "
            "ORDER BY query_index, selection_rank LIMIT 1",
            (period,),
        ).fetchone()

    def save_search(
        self,
        period: str,
        index: int,
        word: str,
        start: str,
        end: str,
        ids: list[str],
        selected_ids: list[str],
    ) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO searches(period,query_index,word,window_start,window_end,"
                "ids_json,selected_ids_json) VALUES(?,?,?,?,?,?,?)",
                (
                    period,
                    index,
                    word,
                    start,
                    end,
                    json.dumps(ids),
                    json.dumps(selected_ids),
                ),
            )

    def save_videos(self, search, items: list[dict], min_views: int) -> None:
        period = search["period"]
        lower, upper = PERIODS[period]
        ids = json.loads(search["selected_ids_json"])
        order = {video_id: rank for rank, video_id in enumerate(ids)}
        with self.db:
            for item in items:
                video_id = item["id"]
                snippet = item.get("snippet", {})
                stats = item.get("statistics", {})
                published = snippet.get("publishedAt", "")
                views = int(stats.get("viewCount", 0))
                language = (
                    snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage") or ""
                )
                if (
                    video_id not in order
                    or not lower <= published < upper
                    or views < min_views
                    or not language.lower().startswith("en")
                    or int(stats.get("commentCount", 0)) < 1
                ):
                    continue
                self.db.execute(
                    "INSERT OR IGNORE INTO videos "
                    "(video_id,period,query_index,selection_rank,title,channel_title,"
                    "published_at,view_count,comment_count,language) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        video_id,
                        period,
                        search["query_index"],
                        order[video_id],
                        html.unescape(snippet.get("title", "")),
                        html.unescape(snippet.get("channelTitle", "")),
                        published,
                        views,
                        int(stats["commentCount"]),
                        language,
                    ),
                )
            self.db.execute(
                "UPDATE searches SET expanded=1 WHERE period=? AND query_index=?",
                (period, search["query_index"]),
            )

    def save_page(self, video, payload: dict, min_chars: int) -> int:
        next_token = payload.get("nextPageToken") or ""
        if (
            next_token
            and self.db.execute(
                "SELECT 1 FROM page_tokens WHERE video_id=? AND token=?",
                (video["video_id"], next_token),
            ).fetchone()
        ):
            raise CollectionError("YouTube returned a repeated comment page token")
        inserted = 0
        rejected_short = rejected_language = 0
        with self.db:
            if next_token:
                self.db.execute(
                    "INSERT INTO page_tokens VALUES(?,?)", (video["video_id"], next_token)
                )
            for item in payload.get("items", []):
                comment = item["snippet"]["topLevelComment"]["snippet"]
                likes = int(comment.get("likeCount", 0))
                value = mask_contacts(clean_text(comment.get("textDisplay", "")))
                if len(value.strip()) < min_chars:
                    rejected_short += 1
                    continue
                if not is_english(value):
                    rejected_language += 1
                    continue
                cursor = self.db.execute(
                    "INSERT OR IGNORE INTO comments VALUES(?,?,?,?,?,?,?,?)",
                    (
                        item["id"],
                        video["video_id"],
                        video["period"],
                        period_of(comment["publishedAt"]),
                        value,
                        likes,
                        comment["publishedAt"],
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                inserted += cursor.rowcount
            self.db.execute(
                "UPDATE videos SET page_token=?, pages_done=pages_done+1, done=?, "
                "rejected_short=rejected_short+?, rejected_language=rejected_language+? "
                "WHERE video_id=?",
                (
                    next_token,
                    int(not next_token),
                    rejected_short,
                    rejected_language,
                    video["video_id"],
                ),
            )
        return inserted

    def skip_video(self, video_id: str) -> None:
        with self.db:
            self.db.execute("UPDATE videos SET done=1 WHERE video_id=?", (video_id,))


def collect(
    client: YouTubeAPIClient,
    database: Path,
    words_path: Path,
    *,
    target: int,
    seed: int,
    min_views: int = 10000,
    min_chars: int = 20,
    videos_per_query: int = 10,
    progress=None,
) -> dict[str, int]:
    if target < 1 or seed < 0 or min_views < 0 or min_chars < 1 or not 1 <= videos_per_query <= 50:
        raise ValueError("Invalid sampling limits or seed")
    words = vocabulary(words_path)
    config = {
        "seed": seed,
        "vocabulary_sha256": hashlib.sha256(words_path.read_bytes()).hexdigest(),
        "min_views": min_views,
        "min_chars": min_chars,
        "videos_per_query": videos_per_query,
        "periods": PERIODS,
        "search_order": "relevance",
        "comment_order": "time",
        "language_filter": "langdetect en>=0.90",
        "version": 7,
    }
    quota = {"pre_chatgpt": (target + 1) // 2, "post_chatgpt": target // 2}
    with locked(database):
        store = SampleStore(database, config)
        try:
            while any(store.count(p) < quota[p] for p in PERIODS):
                # Prioritize the less-filled period; ties start with the older group.
                period = min(
                    (p for p in PERIODS if store.count(p) < quota[p]),
                    key=lambda p: store.count(p) / quota[p],
                )
                video = store.pending_video(period)
                if video:
                    params = {
                        "part": "snippet",
                        "videoId": video["video_id"],
                        "maxResults": 100,
                        "order": "time",
                        "textFormat": "plainText",
                        "fields": COMMENT_FIELDS,
                    }
                    if video["page_token"]:
                        params["pageToken"] = video["page_token"]
                    try:
                        page = client.get("commentThreads", params)
                    except CollectionError as error:
                        if "comments are disabled" not in str(error):
                            raise
                        store.skip_video(video["video_id"])
                        continue
                    inserted = store.save_page(video, page, min_chars)
                    if progress:
                        progress(
                            f"comments period={period} video={video['video_id']} "
                            f"fetched={len(page.get('items', []))} accepted={inserted} "
                            f"total={sum(store.count(p) for p in PERIODS)}/{target} "
                            f"api_requests={client.request_count}"
                        )
                    continue
                search = store.unexpanded(period)
                if search:
                    ids = json.loads(search["selected_ids_json"])
                    items = []
                    if ids:
                        items = client.get(
                            "videos",
                            {
                                "part": "snippet,statistics",
                                "id": ",".join(ids),
                                "fields": VIDEO_FIELDS,
                            },
                        ).get("items", [])
                    store.save_videos(search, items, min_views)
                    if progress:
                        progress(
                            f"videos period={period} checked={len(items)} "
                            f"api_requests={client.request_count}"
                        )
                    continue
                index = store.next_index(period)
                word, lower, upper = query_for(words, seed, period, index)
                result = client.get(
                    "search",
                    {
                        "part": "snippet",
                        "type": "video",
                        "q": word,
                        "relevanceLanguage": "en",
                        "publishedAfter": lower,
                        "publishedBefore": upper,
                        "order": "relevance",
                        "maxResults": 50,
                        "fields": SEARCH_FIELDS,
                    },
                )
                ids = list(
                    dict.fromkeys(
                        item.get("id", {}).get("videoId")
                        for item in result.get("items", [])
                        if item.get("id", {}).get("videoId")
                    )
                )
                selected_ids = ids.copy()
                random.Random(derived_seed(seed, "videos", period, index)).shuffle(selected_ids)
                store.save_search(
                    period, index, word, lower, upper, ids, selected_ids[:videos_per_query]
                )
                if progress:
                    progress(
                        f"search period={period} query={index} word={word} "
                        f"found={len(ids)} api_requests={client.request_count}"
                    )
            return {p: store.count(p) for p in PERIODS}
        finally:
            store.close()


def select_for_labeling(rows: list[sqlite3.Row], count: int, seed: int) -> list[sqlite3.Row]:
    """Balance periods and cycle videos using stable seeded orders."""
    quotas = {"pre_chatgpt": (count + 1) // 2, "post_chatgpt": count // 2}
    available = {period: 0 for period in PERIODS}
    for row in rows:
        available[row["comment_period"]] += 1
    for period, needed in quotas.items():
        if available[period] < needed:
            raise ValueError(
                f"Cannot export {count} balanced tasks: {period} has "
                f"{available[period]} comments, needs {needed}"
            )
    groups = defaultdict(list)
    for row in rows:
        groups[(row["comment_period"], row["video_id"])].append(row)
    periods = {}
    for period in PERIODS:
        video_ids = sorted(
            (video_id for p, video_id in groups if p == period),
            key=lambda video_id: derived_seed(seed, "export-video", period, video_id),
        )
        videos = [
            deque(
                sorted(
                    groups[(period, video_id)],
                    key=lambda row: derived_seed(seed, "export-comment", row["comment_id"]),
                )
            )
            for video_id in video_ids
        ]
        ordered = []
        while videos:
            remaining = []
            for video in videos:
                ordered.append(video.popleft())
                if video:
                    remaining.append(video)
            videos = remaining
        periods[period] = deque(ordered)
    selected = []
    for index in range(count):
        period = "pre_chatgpt" if index % 2 == 0 else "post_chatgpt"
        selected.append(periods[period].popleft())
    return selected


def export_label_studio(
    database: Path,
    output: Path,
    batch_size: int = 1000,
    *,
    export_count: int | None = None,
    seed: int = 20261025,
) -> int:
    """Write importable JSON arrays, optionally sampling a seeded diverse subset."""
    if batch_size < 1 or seed < 0 or (export_count is not None and export_count < 1):
        raise ValueError("Batch size and export count must be positive; seed must be nonnegative")
    if output.exists() and any(output.iterdir()):
        raise ValueError("Export directory must be empty to avoid duplicate Label Studio tasks")
    with sqlite3.connect(database) as db:
        db.row_factory = sqlite3.Row
        rows = list(
            db.execute(
                "SELECT c.*,v.title,v.published_at AS video_published_at,v.view_count,"
                "s.word AS search_query "
                "FROM comments c JOIN videos v USING(video_id) "
                "JOIN searches s ON s.period=v.period AND s.query_index=v.query_index "
                "ORDER BY c.comment_period,c.video_id,c.comment_id"
            )
        )
        if export_count is not None:
            if export_count > len(rows):
                raise ValueError(f"Requested {export_count} tasks, but only {len(rows)} are stored")
            rows = select_for_labeling(rows, export_count, seed)
        output.mkdir(parents=True, exist_ok=True)
        count = 0
        stream = None
        try:
            for row in rows:
                if count % batch_size == 0:
                    if stream:
                        stream.write("]\n")
                        stream.close()
                    stream = (output / f"tasks_{count // batch_size:04d}.json").open(
                        "w", encoding="utf-8"
                    )
                    stream.write("[\n")
                task = {
                    "data": {
                        "comment_id": row["comment_id"],
                        "video_id": row["video_id"],
                        "video_period": row["video_period"],
                        "comment_period": row["comment_period"],
                        "text": row["text_clean"],
                        "comment_published_at": row["published_at"],
                        "video_published_at": row["video_published_at"],
                        "like_count": row["like_count"],
                        "view_count": row["view_count"],
                        "video_title": row["title"],
                        "search_query": row["search_query"],
                    }
                }
                if count % batch_size:
                    stream.write(",\n")
                stream.write(json.dumps(task, ensure_ascii=False))
                count += 1
            if stream:
                stream.write("\n]\n")
        finally:
            if stream and not stream.closed:
                stream.close()
    return count
