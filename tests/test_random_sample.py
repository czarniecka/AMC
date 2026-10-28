"""The random sample keeps its cursor and identities across quota interruptions."""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from amc.youtube.api_client import CollectionStopped
from amc.youtube.random_sample import (
    PERIODS,
    collect,
    export_label_studio,
    is_english,
    period_of,
    query_for,
    vocabulary,
)


class FakeClient:
    def __init__(self, budget: int) -> None:
        self.budget = budget
        self.request_count = 0
        self.calls = []

    def get(self, resource, params):
        if self.request_count == self.budget:
            raise CollectionStopped("Local API request budget reached")
        self.request_count += 1
        self.calls.append((resource, params))
        period = (
            "pre_chatgpt"
            if params.get("publishedAfter", "2023") < PERIODS["pre_chatgpt"][1]
            else "post_chatgpt"
        )
        if resource == "search":
            return {"items": [{"id": {"videoId": period}}]}
        if resource == "videos":
            video_id = params["id"]
            return {
                "items": [
                    {
                        "id": video_id,
                        "snippet": {
                            "title": "A video",
                            "channelTitle": "Channel",
                            "publishedAt": "2022-11-29T00:00:00Z"
                            if video_id == "pre_chatgpt"
                            else "2022-11-30T00:00:00Z",
                            "defaultAudioLanguage": "en",
                        },
                        "statistics": {"viewCount": "10000", "commentCount": "200"},
                    }
                ]
            }
        video_id = params["videoId"]
        page = 2 if params.get("pageToken") else 1
        return {
            "items": [
                {
                    "id": f"{video_id}-comment-{page}",
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "textDisplay": (
                                    "This is an English comment about the video and its story, "
                                    f"page {page}."
                                ),
                                "likeCount": 0,
                                "publishedAt": (
                                    "2022-11-29T12:00:00Z"
                                    if video_id == "pre_chatgpt"
                                    else "2022-11-30T12:00:00Z"
                                ),
                            }
                        }
                    },
                },
                {
                    "id": f"{video_id}-short-{page}",
                    "snippet": {
                        "topLevelComment": {
                            "snippet": {
                                "textDisplay": "Great!",
                                "likeCount": 0,
                                "publishedAt": "2022-11-30T12:00:00Z",
                            }
                        }
                    },
                },
            ],
            **({"nextPageToken": "next"} if page == 1 else {}),
        }


class RandomSampleTests(unittest.TestCase):
    def test_chatgpt_cutoff_uses_comment_date(self):
        self.assertEqual(period_of("2022-11-29T23:59:59Z"), "pre_chatgpt")
        self.assertEqual(period_of("2022-11-30T00:00:00Z"), "post_chatgpt")
        self.assertEqual(period_of("2024-01-01T00:00:00Z"), "post_chatgpt")

    def test_language_screen_is_deterministic_and_conservative(self):
        english = "This is a clear English sentence about a book and a beautiful garden."
        polish = "To jest polskie zdanie o książce i pięknym ogrodzie."
        self.assertTrue(is_english(english))
        self.assertFalse(is_english(polish))
        self.assertFalse(is_english("AI"))

    def test_query_schedule_is_seeded_unique_and_period_bounded(self):
        words = ("apple", "book")
        schedule = [query_for(words, 77, "pre_chatgpt", i) for i in range(32)]
        self.assertEqual(len(set(schedule)), 32)
        self.assertTrue(all(end <= "2022-11-30T00:00:00Z" for _, _, end in schedule))
        self.assertEqual(schedule, [query_for(words, 77, "pre_chatgpt", i) for i in range(32)])
        post_schedule = [query_for(words, 77, "post_chatgpt", i) for i in range(34)]
        self.assertEqual(len(set(post_schedule)), 34)
        self.assertTrue(all(start >= "2022-11-30T00:00:00Z" for _, start, _ in post_schedule))

    def test_work_queries_allow_phrases_without_ai_terms(self):
        path = Path(__file__).resolve().parents[1] / "config/youtube/work_queries.txt"
        queries = vocabulary(path)
        self.assertIn("entry level jobs", queries)
        self.assertIn("will robots take our jobs", queries)
        self.assertTrue(all("ai" not in query.split() for query in queries))

    def test_resume_after_page_and_raise_target_without_duplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            words = root / "words.txt"
            words.write_text("apple\nbook\n", encoding="utf-8")
            database = root / "sample.sqlite3"
            options = dict(target=2, seed=77)
            with self.assertRaises(CollectionStopped):
                collect(FakeClient(3), database, words, **options)
            with sqlite3.connect(database) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM comments").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT page_token FROM videos").fetchone()[0], "next")
                self.assertEqual(
                    db.execute("SELECT SUM(rejected_short) FROM videos").fetchone()[0], 1
                )
            resumed = FakeClient(10)
            self.assertEqual(
                collect(resumed, database, words, target=4, seed=77),
                {"pre_chatgpt": 2, "post_chatgpt": 2},
            )
            resumed_page = next(
                params
                for resource, params in resumed.calls
                if resource == "commentThreads" and params["videoId"] == "pre_chatgpt"
            )
            self.assertEqual(resumed_page["pageToken"], "next")
            self.assertEqual(
                collect(FakeClient(0), database, words, target=4, seed=77),
                {"pre_chatgpt": 2, "post_chatgpt": 2},
            )
            with self.assertRaisesRegex(ValueError, "settings changed"):
                collect(FakeClient(0), database, words, target=4, seed=78)
            exported = root / "label_studio"
            self.assertEqual(export_label_studio(database, exported, batch_size=3), 4)
            tasks = []
            for path in sorted(exported.glob("*.json")):
                tasks.extend(json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(len(tasks), 4)
            self.assertEqual(len({task["data"]["comment_id"] for task in tasks}), 4)
            self.assertTrue(all(task["data"]["video_title"] == "A video" for task in tasks))
            self.assertTrue(
                all(task["data"]["search_query"] in {"apple", "book"} for task in tasks)
            )
            self.assertTrue(
                all(task["data"]["text"].startswith("This is an English") for task in tasks)
            )
            self.assertEqual(
                {task["data"]["comment_period"] for task in tasks},
                {"pre_chatgpt", "post_chatgpt"},
            )
            self.assertEqual(
                {task["data"]["video_period"] for task in tasks},
                {"pre_chatgpt", "post_chatgpt"},
            )
            sample_a = root / "sample_a"
            sample_b = root / "sample_b"
            self.assertEqual(export_label_studio(database, sample_a, export_count=2, seed=77), 2)
            self.assertEqual(export_label_studio(database, sample_b, export_count=2, seed=77), 2)
            self.assertEqual(
                (sample_a / "tasks_0000.json").read_bytes(),
                (sample_b / "tasks_0000.json").read_bytes(),
            )
            subset = json.loads((sample_a / "tasks_0000.json").read_text())
            self.assertEqual({task["data"]["comment_period"] for task in subset}, set(PERIODS))
            with self.assertRaisesRegex(ValueError, "only 4 are stored"):
                export_label_studio(database, root / "too_many", export_count=5)
            with sqlite3.connect(database) as db:
                db.execute(
                    "UPDATE comments SET comment_period='post_chatgpt' "
                    "WHERE comment_id='pre_chatgpt-comment-1'"
                )
            with self.assertRaisesRegex(ValueError, "pre_chatgpt has 1 comments, needs 2"):
                export_label_studio(database, root / "unbalanced", export_count=4)


if __name__ == "__main__":
    unittest.main()
