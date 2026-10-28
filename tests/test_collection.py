"""Offline tests for request bounds, privacy selection, and failure recovery."""

import csv
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

import requests
from youtube_transcript_api import (
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    YouTubeRequestFailed,
)

from amc.youtube.__main__ import main
from amc.youtube.api_client import CollectionError, CollectionStopped, YouTubeAPIClient
from amc.youtube.collector import CollectorConfig, YouTubeDataCollector
from amc.youtube.comment_extractor import COMMENT_FIELDS, extract_comments
from amc.youtube.exporter import COMMENT_COLUMNS, export_collection
from amc.youtube.models import Comment, SearchQuery, Transcript, VideoMetadata
from amc.youtube.transcript_fetcher import TranscriptFetcher, TranscriptHTTPSession
from amc.youtube.video_finder import find_videos, rank_videos


def response(status: int, payload: object) -> requests.Response:
    result = requests.Response()
    result.status_code = status
    result._content = json.dumps(payload).encode("utf-8")
    result._content_consumed = True
    return result


def comment_page(count: int, next_token: str | None = None) -> dict:
    result = {
        "items": [
            {
                "snippet": {
                    "topLevelComment": {
                        "snippet": {
                            "textDisplay": "Zażółć\n gęślą &amp; AI"
                            + (f" {index}" if index else ""),
                            "likeCount": 2,
                            "publishedAt": "2024-02-01T00:00:00Z",
                        }
                    }
                }
            }
            for index in range(count)
        ]
    }
    if next_token:
        result["nextPageToken"] = next_token
    return result


def video_item(video_id: str, count: int | None, date: str = "2024-01-01T00:00:00Z") -> dict:
    return {
        "id": video_id,
        "snippet": {"title": "AI &amp; skills", "channelTitle": "Channel", "publishedAt": date},
        "statistics": {} if count is None else {"viewCount": "100", "commentCount": str(count)},
    }


class APIClientTests(unittest.TestCase):
    def test_missing_key_has_clear_message(self):
        with patch.dict("os.environ", {"YOUTUBE_API_KEY": ""}):
            with self.assertRaisesRegex(CollectionError, "YOUTUBE_API_KEY"):
                YouTubeAPIClient()

    def test_403_and_429_stop_without_retry_or_secret(self):
        for status, reason in ((403, "quotaExceeded"), (403, "commentsDisabled"), (429, "")):
            with self.subTest(status=status, reason=reason):
                session = Mock(spec=requests.Session)
                session.get.return_value = response(
                    status, {"error": {"errors": [{"reason": reason}]}}
                )
                client = YouTubeAPIClient("private-api-key", session=session)
                with self.assertRaises(CollectionStopped) as caught:
                    client.get("search", {"fields": "items/id"})
                self.assertNotIn("private-api-key", str(caught.exception))
                self.assertIn(str(status), str(caught.exception))
                self.assertEqual(session.get.call_count, 1)

    def test_transient_server_retry_is_bounded(self):
        session = Mock(spec=requests.Session)
        session.get.side_effect = [response(503, {}), response(200, {"items": []})]
        sleeper = Mock()
        client = YouTubeAPIClient("key", session=session, sleeper=sleeper)
        self.assertEqual(client.get("search", {"fields": "items/id"}), {"items": []})
        self.assertEqual(client.request_count, 2)
        sleeper.assert_called_once_with(1)

    def test_local_budget_prevents_extra_network_call(self):
        session = Mock(spec=requests.Session)
        session.get.return_value = response(200, {})
        client = YouTubeAPIClient("key", session=session, max_requests=1)
        client.get("search", {"fields": "items/id"})
        with self.assertRaisesRegex(CollectionStopped, "budget"):
            client.get("search", {"fields": "items/id"})
        self.assertEqual(session.get.call_count, 1)

    def test_connection_failure_does_not_expose_request_details(self):
        session = Mock(spec=requests.Session)
        session.get.side_effect = requests.Timeout("URL containing private-api-key")
        client = YouTubeAPIClient("private-api-key", session=session)
        with self.assertRaises(CollectionError) as caught:
            client.get("search", {"fields": "items/id"})
        self.assertNotIn("private-api-key", str(caught.exception))

    def test_response_allowlist_is_mandatory(self):
        session = Mock(spec=requests.Session)
        client = YouTubeAPIClient("key", session=session)
        with self.assertRaises(ValueError):
            client.get("commentThreads", {"part": "snippet"})
        session.get.assert_not_called()


class FinderTests(unittest.TestCase):
    def test_bilingual_search_pagination_deduplication_cutoff_and_ranking(self):
        client = Mock(spec=YouTubeAPIClient)
        client.get.side_effect = [
            {
                "items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "boundary"}}],
                "nextPageToken": "next",
            },
            {"items": [video_item("a", 5), video_item("boundary", 999, "2023-01-01T00:00:00Z")]},
            {"items": [{"id": {"videoId": "b"}}]},
            {"items": [video_item("b", 10)]},
            {"items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "c"}}]},
            {"items": [video_item("c", None)]},
        ]
        result = find_videos(client, (SearchQuery("AI praca", "pl"), SearchQuery("AI jobs", "en")))
        self.assertEqual([video.video_id for video in result], ["b", "a", "c"])
        self.assertIsNone(result[-1].comment_count)
        self.assertEqual(result[0].title, "AI & skills")
        searches = [call.args[1] for call in client.get.call_args_list if call.args[0] == "search"]
        self.assertEqual([query["relevanceLanguage"] for query in searches], ["pl", "pl", "en"])
        self.assertEqual(searches[1]["pageToken"], "next")
        self.assertTrue(all(query["order"] == "relevance" for query in searches))
        self.assertTrue(
            all(query["publishedAfter"] == "2023-01-01T00:00:00Z" for query in searches)
        )

    def test_video_limit_is_applied_after_ranking(self):
        videos = [
            VideoMetadata(str(count), "t", "c", "2024-01-01", 1, count) for count in (1, 100, 5)
        ]
        self.assertEqual([video.comment_count for video in rank_videos(videos, 2)], [100, 5])


class CommentTests(unittest.TestCase):
    def test_pagination_limit_uuid_and_author_fields_excluded(self):
        client = Mock(spec=YouTubeAPIClient)
        client.get.side_effect = [comment_page(100, "second"), comment_page(50, "third")]
        result = list(extract_comments(client, "video", max_comments=150))
        self.assertEqual(len(result), 150)
        self.assertEqual(client.get.call_count, 2)
        self.assertEqual(client.get.call_args_list[1].args[1]["maxResults"], 50)
        self.assertEqual(client.get.call_args_list[1].args[1]["pageToken"], "second")
        self.assertEqual(result[0].text_clean, "Zażółć gęślą & AI")
        self.assertTrue(all(UUID(row.comment_id).version == 4 for row in result))
        self.assertEqual(len({row.comment_id for row in result}), 150)
        for call in client.get.call_args_list:
            self.assertEqual(call.args[1]["fields"], COMMENT_FIELDS)
            self.assertEqual(call.args[1]["part"], "snippet")
            self.assertEqual(call.args[1]["textFormat"], "plainText")
            self.assertNotIn("author", call.args[1]["fields"].lower())
            self.assertNotIn("id", call.args[1]["fields"].lower())

    def test_maximum_of_5000_is_enforced(self):
        with self.assertRaises(ValueError):
            list(extract_comments(Mock(), "video", max_comments=5001))

    def test_exactly_500_comments_uses_five_pages_and_stops(self):
        client = Mock(spec=YouTubeAPIClient)
        client.get.side_effect = [comment_page(100, str(index)) for index in range(5)]
        result = list(extract_comments(client, "video", max_comments=500))
        self.assertEqual(len(result), 500)
        self.assertEqual(client.get.call_count, 5)

    def test_zero_comments_does_not_request(self):
        client = Mock(spec=YouTubeAPIClient)
        self.assertEqual(list(extract_comments(client, "video", max_comments=0)), [])
        client.get.assert_not_called()

    def test_repeated_page_token_is_stopped(self):
        client = Mock(spec=YouTubeAPIClient)
        client.get.side_effect = [comment_page(1, "same"), comment_page(1, "same")]
        with self.assertRaisesRegex(CollectionError, "repeated"):
            list(extract_comments(client, "video"))


class TranscriptTests(unittest.TestCase):
    def test_join_languages_and_sleep_between_fetches(self):
        api = Mock()
        api.fetch.return_value = [
            SimpleNamespace(text="AI\n skills"),
            SimpleNamespace(text="today"),
        ]
        sleeper = Mock()
        fetcher = TranscriptFetcher(api, sleeper=sleeper, delay=lambda: 0.75)
        self.assertEqual(fetcher.fetch("a").transcript, "AI skills today")
        sleeper.assert_not_called()
        fetcher.fetch("b")
        sleeper.assert_called_once_with(0.75)
        api.fetch.assert_called_with("b", languages=["pl", "en"])

    def test_missing_and_disabled_captions_return_none_and_continue(self):
        api = Mock()
        api.fetch.side_effect = [
            TranscriptsDisabled("a"),
            NoTranscriptFound("b", ["pl", "en"], {}),
            [SimpleNamespace(text="available")],
        ]
        fetcher = TranscriptFetcher(api, sleeper=Mock())
        self.assertIsNone(fetcher.fetch("a").transcript)
        self.assertIsNone(fetcher.fetch("b").transcript)
        self.assertEqual(fetcher.fetch("c").transcript, "available")

    def test_blocked_transcripts_stop_collection(self):
        api = Mock()
        api.fetch.side_effect = RequestBlocked("a")
        with self.assertRaises(CollectionStopped):
            TranscriptFetcher(api).fetch("a")

    def test_http_session_stops_before_library_wraps_rate_errors(self):
        for status in (403, 429):
            with self.subTest(status=status):
                with patch.object(
                    requests.Session, "request", return_value=response(status, {})
                ) as call:
                    with self.assertRaises(CollectionStopped):
                        TranscriptHTTPSession().get("https://www.youtube.com")
                    self.assertEqual(call.call_args.kwargs["timeout"], (5, 30))

    def test_wrapped_http_error_is_not_treated_as_missing_captions(self):
        api = Mock()
        error = YouTubeRequestFailed("a", requests.HTTPError("private URL"))
        api.fetch.side_effect = error
        with self.assertRaisesRegex(CollectionError, "HTTP request failed"):
            TranscriptFetcher(api).fetch("a")


class ExportAndCollectorTests(unittest.TestCase):
    def test_complete_run_keeps_collecting_after_missing_transcript(self):
        client = Mock(spec=YouTubeAPIClient)
        client.get.side_effect = [
            {"items": [{"id": {"videoId": "a"}}, {"id": {"videoId": "b"}}]},
            {"items": [video_item("a", 10), video_item("b", 5)]},
            comment_page(1),
            comment_page(1),
        ]
        captions = Mock(spec=TranscriptFetcher)
        captions.fetch.side_effect = [Transcript("a", None), Transcript("b", "AI skills")]
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            config = CollectorConfig(
                queries=(SearchQuery("AI", "en"),),
                output_dir=Path(directory),
                include_transcripts=True,
            )
            result = YouTubeDataCollector(client, config, transcript_fetcher=captions).collect()
            self.assertIsNone(result.stopped_reason)
            self.assertEqual(len(result.comments), 2)
            self.assertEqual(
                result.transcripts, [Transcript("a", None), Transcript("b", "AI skills")]
            )
            self.assertEqual(len(list(Path(directory).glob("*.csv"))), 4)
            captions.close.assert_called_once()

    def test_csv_headers_bom_unicode_formula_protection_and_none(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory)
            comment = Comment("video", "uuid", "=Zażółć", 2, "2024-01-01")
            export_collection(output, [], [comment], [Transcript("video", None)])
            path = output / "yt_comments_anonymized.csv"
            self.assertTrue(path.read_bytes().startswith(b"\xef\xbb\xbf"))
            with path.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(reader.fieldnames, list(COMMENT_COLUMNS))
                self.assertEqual(next(reader)["text_clean"], "'=Zażółć")
            with (output / "yt_transcripts.csv").open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual(next(csv.DictReader(stream))["transcript"], "")
            self.assertEqual(len(list(output.glob("*.csv"))), 3)
            self.assertFalse(list(output.glob("*.tmp")))

    def test_partial_comment_pages_exported_and_no_more_requests_after_stop(self):
        client = Mock(spec=YouTubeAPIClient)
        client.get.side_effect = [
            {"items": [{"id": {"videoId": "video"}}]},
            {"items": [video_item("video", 500)]},
            comment_page(2, "next"),
            CollectionStopped("YouTube HTTP 429: stopped"),
        ]
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            config = CollectorConfig(queries=(SearchQuery("AI", "en"),), output_dir=Path(directory))
            with self.assertLogs("amc.youtube.collector", level="ERROR"):
                result = YouTubeDataCollector(client, config).collect()
            self.assertEqual(len(result.comments), 2)
            self.assertIn("429", result.stopped_reason)
            self.assertEqual(client.get.call_count, 4)
            self.assertEqual(result.transcripts, [Transcript("video", None)])
            with (Path(directory) / "yt_comments_anonymized.csv").open(
                encoding="utf-8-sig"
            ) as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 2)

    def test_partial_search_metadata_is_preserved(self):
        client = Mock(spec=YouTubeAPIClient)
        client.get.side_effect = [
            {"items": [{"id": {"videoId": "a"}}], "nextPageToken": "next"},
            {"items": [video_item("a", 5)]},
            CollectionStopped("Budget reached"),
        ]
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            config = CollectorConfig(queries=(SearchQuery("AI", "en"),), output_dir=Path(directory))
            with self.assertLogs("amc.youtube.collector", level="ERROR"):
                result = YouTubeDataCollector(client, config).collect()
            self.assertEqual([video.video_id for video in result.videos], ["a"])
            self.assertFalse(result.comments)

    def test_invalid_limits_are_rejected_before_network_access(self):
        for kwargs in ({"max_comments": 5001}, {"max_videos": 0}, {"candidates_per_query": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CollectorConfig(**kwargs)

    def test_cli_missing_key_has_no_traceback(self):
        with (
            patch.dict("os.environ", {"YOUTUBE_API_KEY": ""}),
            redirect_stderr(io.StringIO()) as stream,
        ):
            self.assertEqual(main([]), 2)
        self.assertIn("YOUTUBE_API_KEY", stream.getvalue())
        self.assertNotIn("Traceback", stream.getvalue())
