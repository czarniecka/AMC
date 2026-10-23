"""Preserve blind texts and protect manual work from concurrent changes."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from amc.youtube.annotation import disagreements, load_sheet, save_label
from amc.youtube.validation import KEY, SHEET, fingerprint, write_new


class AnnotationTests(unittest.TestCase):
    def test_disagreement_filter_matches_text_and_prediction_cohort(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            path = self.sheet(root)
            rows, _ = load_sheet(path)
            rows[0].update(relevance="relevant", impact="positive")
            write_new(
                root / "key.csv",
                KEY,
                [
                    {
                        "sample_id": "P001",
                        "split": "pilot",
                        "video_id": "v",
                        "comment_id": "c",
                        "text_hash": fingerprint(rows[0]["text_clean"]),
                    }
                ],
            )
            prediction = {
                "video_id": "v",
                "comment_id": "c",
                "text_hash": fingerprint(rows[0]["text_clean"]),
                "model": "qwen",
                "prompt_hash": "hash",
                "relevance": "relevant",
                "impact": "mixed",
            }
            write_new(root / "predictions.csv", tuple(prediction), [prediction])
            self.assertEqual(
                disagreements(rows, root / "key.csv", root / "predictions.csv", ("qwen", "hash")),
                [0],
            )
            rows[0]["impact"] = "mixed"
            self.assertEqual(
                disagreements(rows, root / "key.csv", root / "predictions.csv", ("qwen", "hash")),
                [],
            )

    def sheet(self, root):
        path = root / "pilot_annotator_a.csv"
        write_new(
            path,
            SHEET,
            [
                {
                    "sample_id": "P001",
                    "text_clean": "'=AI helps at work",
                    "relevance": "",
                    "impact": "",
                    "note": "",
                }
            ],
        )
        return path

    def test_save_preserves_text_and_original_backup(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = self.sheet(Path(directory))
            original = path.read_bytes()
            _, digest = load_sheet(path)
            save_label(path, "P001", "relevant", "positive", "reviewed", digest)
            rows, _ = load_sheet(path)
            self.assertEqual(rows[0]["text_clean"], "'=AI helps at work")
            self.assertEqual(rows[0]["impact"], "positive")
            self.assertEqual(next((path.parent / "backups").iterdir()).read_bytes(), original)
            with self.assertRaisesRegex(ValueError, "Someone changed"):
                save_label(path, "P001", "relevant", "negative", "", digest)
            self.assertFalse(path.with_suffix(".csv.edit.lock").exists())

    def test_invalid_combination_is_not_saved(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = self.sheet(Path(directory))
            original = path.read_bytes()
            _, digest = load_sheet(path)
            with self.assertRaises(ValueError):
                save_label(path, "P001", "unrelated", "positive", "", digest)
            self.assertEqual(path.read_bytes(), original)

    def test_buttons_save_real_sheet_without_model(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = self.sheet(Path(directory))
            with patch("amc.web.annotate.DIRECTORY", path.parent):
                app = AppTest.from_file(str(Path("amc/web/pages/1_Annotate.py").resolve())).run()
                self.assertEqual(len(app.exception), 0)
                self.assertTrue(app.button[-1].disabled)
                app.radio[0].set_value("Unrelated").run()
                app.button[-1].click().run()
                self.assertEqual(len(app.exception), 0)
            rows, _ = load_sheet(path)
            self.assertEqual(rows[0]["relevance"], "unrelated")
            self.assertEqual(rows[0]["impact"], "unclear")
