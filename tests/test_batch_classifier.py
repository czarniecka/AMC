"""Verify resumable predictions and preservation after a model failure."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from amc.classification.batch_classifier import COLUMNS, read_rows, run


class BatchTests(unittest.TestCase):
    def source(self, root):
        path = root / "comments.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["video_id", "comment_id", "text_clean"])
            writer.writerow(["video", "one", "AI helps me work"])
            writer.writerow(["video", "two", "I fear job loss"])
        return path

    @patch("amc.classification.batch_classifier.classify")
    def test_limit_and_resume_preserve_source(self, model):
        model.return_value = {"relevance": "relevant", "impact": "positive"}
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = self.source(root)
            original = source.read_bytes()
            output = root / "labels.csv"
            self.assertEqual(run(source, output, "qwen3:8b", 1), 1)
            self.assertEqual(run(source, output, "qwen3:8b"), 1)
            self.assertEqual(run(source, output, "qwen3:8b"), 0)
            self.assertEqual(len(read_rows(output, COLUMNS)), 2)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(model.call_count, 2)

    @patch("amc.classification.batch_classifier.classify")
    def test_failure_retains_completed_prediction(self, model):
        model.side_effect = [
            {"relevance": "relevant", "impact": "positive"},
            ValueError("bad response"),
        ]
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            output = root / "labels.csv"
            with self.assertRaises(ValueError):
                run(self.source(root), output, "qwen3:8b")
            self.assertEqual(len(read_rows(output, COLUMNS)), 1)
            self.assertFalse(output.with_suffix(".csv.lock").exists())
