"""Offline checks for frozen small-model screening batches."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from amc.youtube.screening import prepare


class ScreeningTests(unittest.TestCase):
    def test_batches_preserve_identity_and_pre_post_dates(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "comments.csv"
            with source.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(
                    stream,
                    fieldnames=("video_id", "comment_id", "text_clean", "published_at"),
                )
                writer.writeheader()
                writer.writerows(
                    [
                        {
                            "video_id": "v1",
                            "comment_id": "a",
                            "text_clean": "Boję się utraty pracy przez AI",
                            "published_at": "2022-11-29T00:00:00Z",
                        },
                        {
                            "video_id": "v2",
                            "comment_id": "b",
                            "text_clean": "Boję się utraty pracy przez AI",
                            "published_at": "2022-12-01T00:00:00Z",
                        },
                        {
                            "video_id": "v2",
                            "comment_id": "c",
                            "text_clean": "Thanks",
                            "published_at": "2023-01-01T00:00:00Z",
                        },
                    ]
                )
            output = root / "screening"
            result = prepare(source, output, batch_size=2, seed=1)
            self.assertEqual(result, {"comments": 3, "batches": 2})
            batches = [
                json.loads(line) for line in (output / "batches.jsonl").read_text().splitlines()
            ]
            self.assertEqual(sum(len(batch["comments"]) for batch in batches), 3)
            self.assertTrue(all(len(batch["comments"]) <= 2 for batch in batches))
            with (output / "manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
                manifest = list(csv.DictReader(stream))
            self.assertEqual({row["period"] for row in manifest}, {"pre", "post"})
            self.assertEqual({row["comment_id"] for row in manifest}, {"a", "b", "c"})
            self.assertEqual(
                {item["id"] for batch in batches for item in batch["comments"]},
                {row["item_id"] for row in manifest},
            )
            with self.assertRaisesRegex(ValueError, "already exists"):
                prepare(source, output)
