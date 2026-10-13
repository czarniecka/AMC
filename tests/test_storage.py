"""Persistent collection tests covering reruns, legacy imports, and interrupted samples."""

import csv
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from test_collection import comment_page, video_item

from amc.youtube.api_client import CollectionStopped, YouTubeAPIClient
from amc.youtube.collector import CollectorConfig, YouTubeDataCollector
from amc.youtube.exporter import export_collection
from amc.youtube.models import Comment, SearchQuery, Transcript, VideoMetadata
from amc.youtube.storage import CollectionStore


class StorageTests(unittest.TestCase):
    def test_csv_lock_prevents_two_writers(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = CollectionStore(Path(directory))
            try:
                with self.assertRaisesRegex(Exception, "Another collection"):
                    CollectionStore(Path(directory))
            finally:
                store.close()

    def test_sqlite_migration_preserves_completion_and_uuid(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory)
            database = output / "yt_collection.sqlite3"
            with sqlite3.connect(database) as connection:
                connection.executescript("""
                    CREATE TABLE videos(video_id,title,channel_title,
                        published_at,view_count,comment_count);
                    INSERT INTO videos VALUES('a','AI','Channel','2024-01-01',10,10);
                    CREATE TABLE comments(video_id,comment_id,text_clean,like_count,published_at);
                    INSERT INTO comments VALUES('a','saved-uuid','=text',2,'2024-01-02');
                    CREATE TABLE transcripts(video_id,transcript);
                    CREATE TABLE comment_state(video_id,completed,sample_limit,comment_order);
                    INSERT INTO comment_state VALUES('a',0,100,'time');
                """)
            connection.close()
            store = CollectionStore(output)
            self.assertFalse(store.comments_completed("a"))
            self.assertEqual(list(store.comments())[0].comment_id, "saved-uuid")
            self.assertEqual(list(store.comments())[0].text_clean, "=text")
            store.close()
            self.assertFalse(database.exists())
            reopened = CollectionStore(output)
            self.assertEqual(list(reopened.comments())[0].text_clean, "=text")
            reopened.close()

    def test_explicit_selection_ignores_other_cached_videos_and_skips_on_rerun(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = CollectionStore(Path(directory))
            for value in ("aaaaaaaaaaa", "bbbbbbbbbbb"):
                store.save_video(
                    VideoMetadata(value, "AI work", "Channel", "2024-01-01T00:00:00Z", 10, 10)
                )
            store.close()
            config = self.config(directory, video_ids=("aaaaaaaaaaa",), max_comments=1)
            client = Mock(spec=YouTubeAPIClient)
            client.get.return_value = comment_page(1)
            result = YouTubeDataCollector(client, config).collect()
            self.assertEqual(result.total_comments, 1)
            self.assertEqual(client.get.call_count, 1)
            self.assertEqual(client.get.call_args.args[0], "commentThreads")
            self.assertEqual(client.get.call_args.args[1]["videoId"], "aaaaaaaaaaa")
            second = Mock(spec=YouTubeAPIClient)
            YouTubeDataCollector(second, config).collect()
            second.get.assert_not_called()

    def test_unknown_explicit_video_fetches_metadata_without_search(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            client = Mock(spec=YouTubeAPIClient)
            client.get.side_effect = [{"items": [video_item("aaaaaaaaaaa", 5)]}, comment_page(1)]
            result = YouTubeDataCollector(
                client, self.config(directory, video_ids=("aaaaaaaaaaa",))
            ).collect()
            self.assertEqual(result.total_comments, 1)
            self.assertEqual(
                [call.args[0] for call in client.get.call_args_list], ["videos", "commentThreads"]
            )

    def test_invalid_empty_csv_header_preserves_original(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "yt_videos_metadata.csv"
            path.write_text("wrong_header\n", encoding="utf-8")
            with self.assertRaisesRegex(Exception, "Invalid collection CSV"):
                CollectionStore(Path(directory))
            self.assertEqual(path.read_text(), "wrong_header\n")

    def test_missing_comments_with_saved_state_is_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory)
            store = CollectionStore(output)
            store.save_video(VideoMetadata("a", "AI", "Channel", "2024-01-01", 1, 1))
            store.save_comment(Comment("a", "uuid", "Comment", 1, "2024-01-02"))
            store.mark_comments("a", completed=True, limit=1, order="relevance")
            store.close()
            (output / "yt_comments_anonymized.csv").unlink()
            with self.assertRaisesRegex(Exception, "Invalid collection CSV"):
                CollectionStore(output)

    def test_discovery_saves_all_candidates_without_comment_requests(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            client = Mock(spec=YouTubeAPIClient)
            client.get.side_effect = [
                {"items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "b"}}]},
                {"items": [video_item("a", 10), video_item("b", 5)]},
            ]
            result = YouTubeDataCollector(
                client,
                self.config(directory, discover_only=True, max_videos=1),
            ).collect()
            self.assertEqual(result.total_videos, 2)
            self.assertEqual(result.total_comments, 0)
            self.assertEqual(client.get.call_count, 2)
            store = CollectionStore(Path(directory))
            try:
                self.assertFalse(store.comments_completed("a"))
                self.assertFalse(store.comments_completed("b"))
            finally:
                store.close()

    def test_discovery_quota_stop_keeps_metadata_obtained_before_limit(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            client = Mock(spec=YouTubeAPIClient)
            client.get.side_effect = [
                {
                    "items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "b"}}],
                    "nextPageToken": "next",
                },
                {"items": [video_item("a", 10), video_item("b", 5)]},
                CollectionStopped("YouTube HTTP 403: API quota exceeded; stopped."),
            ]
            with self.assertLogs("amc.youtube.collector", level="ERROR"):
                result = YouTubeDataCollector(
                    client,
                    self.config(directory, discover_only=True, max_videos=1),
                ).collect()
            self.assertEqual(result.total_videos, 2)
            self.assertIn("quota", result.stopped_reason)
            self.assertEqual(result.total_comments, 0)

    def config(self, directory: str, **kwargs) -> CollectorConfig:
        return CollectorConfig(
            queries=(SearchQuery("AI", "en"),),
            output_dir=Path(directory),
            **kwargs,
        )

    def initial_client(self, count: int = 1) -> Mock:
        client = Mock(spec=YouTubeAPIClient)
        client.get.side_effect = [
            {"items": [{"id": {"videoId": "a"}}]},
            {"items": [video_item("a", 10)]},
            comment_page(count),
        ]
        return client

    def test_second_run_keeps_exports_and_skips_completed_video_requests(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            config = self.config(directory)
            first = YouTubeDataCollector(self.initial_client(), config).collect()
            second_client = Mock(spec=YouTubeAPIClient)
            second_client.get.return_value = {"items": [{"id": {"videoId": "a"}}]}
            second = YouTubeDataCollector(second_client, config).collect()
            self.assertEqual(second.total_comments, 1)
            self.assertEqual(second.total_videos, 1)
            self.assertEqual(second.comments, [])
            self.assertEqual(second_client.get.call_count, 1)
            self.assertEqual(second_client.get.call_args.args[0], "search")
            with (Path(directory) / "yt_comments_anonymized.csv").open(
                encoding="utf-8-sig"
            ) as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["comment_id"], first.comments[0].comment_id)

    def test_refresh_is_explicit_and_deduplicates_without_changing_saved_ids(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            first = YouTubeDataCollector(self.initial_client(), self.config(directory)).collect()
            client = Mock(spec=YouTubeAPIClient)
            client.get.side_effect = [
                {"items": [{"id": {"videoId": "a"}}]},
                comment_page(2),
            ]
            result = YouTubeDataCollector(
                client,
                self.config(directory, refresh_comments=True, comment_order="time"),
            ).collect()
            self.assertEqual(result.total_comments, 2)
            self.assertEqual(len(result.comments), 1)
            self.assertEqual(client.get.call_args.args[1]["order"], "time")
            store = CollectionStore(Path(directory))
            try:
                self.assertEqual(list(store.comments())[0].comment_id, first.comments[0].comment_id)
            finally:
                store.close()

    def test_partial_retry_does_not_duplicate_already_saved_comments(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            client = self.initial_client()
            client.get.side_effect = [
                {"items": [{"id": {"videoId": "a"}}]},
                {"items": [video_item("a", 10)]},
                comment_page(2, "next"),
                CollectionStopped("Rate limit"),
            ]
            with self.assertLogs("amc.youtube.collector", level="ERROR"):
                first = YouTubeDataCollector(client, self.config(directory)).collect()
            retry = Mock(spec=YouTubeAPIClient)
            retry.get.side_effect = [{"items": [{"id": {"videoId": "a"}}]}, comment_page(2)]
            result = YouTubeDataCollector(retry, self.config(directory)).collect()
            self.assertEqual(result.total_comments, 2)
            self.assertEqual(result.comments, [])
            store = CollectionStore(Path(directory))
            try:
                self.assertTrue(store.comments_completed("a"))
                self.assertEqual(
                    [row.comment_id for row in store.comments()],
                    [row.comment_id for row in first.comments],
                )
            finally:
                store.close()

    def test_legacy_exports_are_backed_up_and_imported_once(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory)
            video = VideoMetadata("a", "AI", "Channel", "2024-01-01", 100, 20)
            comment = Comment("a", "saved-uuid", "Comment", 5, "2024-01-02")
            export_collection(output, [video], [comment], [Transcript("a", None)])
            originals = {path.name: path.read_bytes() for path in output.glob("*.csv")}
            for _ in range(2):
                store = CollectionStore(output)
                try:
                    self.assertEqual(store.videos(), [video])
                    self.assertEqual(list(store.comments()), [comment])
                    self.assertTrue(store.comments_completed("a"))
                finally:
                    store.close()
            backups = list((output / "backups").iterdir())
            self.assertEqual(len(backups), 1)
            for name, content in originals.items():
                self.assertEqual((backups[0] / name).read_bytes(), content)
                self.assertEqual((output / name).read_bytes(), content)

    def test_comment_durability_and_missing_transcript_does_not_erase_existing(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            store = CollectionStore(Path(directory))
            store.save_video(VideoMetadata("a", "AI", "Channel", "2024-01-01", 1, 1))
            first = Comment("a", "uuid-one", "Same text", 5, "2024-01-02")
            self.assertTrue(store.save_comment(first))
            self.assertFalse(
                store.save_comment(Comment("a", "uuid-two", "Same text", 9, "2024-01-02"))
            )
            store.save_transcript(Transcript("a", "Downloaded text"))
            store.save_transcript(Transcript("a", None))
            store.close()
            reopened = CollectionStore(Path(directory))
            try:
                self.assertEqual(list(reopened.comments()), [first])
                self.assertEqual(reopened.transcripts(), [Transcript("a", "Downloaded text")])
            finally:
                reopened.close()
