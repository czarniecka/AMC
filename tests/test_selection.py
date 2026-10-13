"""Validate configurable pilot selections before collection."""

import json
import tempfile
import unittest
from pathlib import Path

from amc.youtube.selection import load_selection


class SelectionTests(unittest.TestCase):
    def test_default_selection_contains_twenty_unique_videos(self):
        ids, limit = load_selection(Path("config/youtube/approved_videos.json"))
        self.assertEqual(len(ids), 20)
        self.assertEqual(limit, 100)

    def test_duplicate_ids_and_invalid_limits_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "selection.json"
            for payload in (
                {"video_ids": ["aaaaaaaaaaa", "aaaaaaaaaaa"]},
                {"video_ids": ["aaaaaaaaaaa"], "max_comments": True},
                {"video_ids": []},
            ):
                path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_selection(path)
