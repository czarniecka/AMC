"""Offline tests for blind splits, human adjudication and strict evaluation."""

import tempfile
import unittest
from pathlib import Path

from amc.youtube.validation import (
    KEY,
    SHEET,
    adjudicate,
    evaluate,
    fingerprint,
    metrics,
    prepare,
    read,
    save_report,
    single_annotator,
    write_new,
)


class ValidationTests(unittest.TestCase):
    def test_single_annotator_is_explicit_and_requires_frozen_text(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            row = dict(zip(SHEET, ("P001", "AI work", "relevant", "neutral", ""), strict=True))
            write_new(root / "sheet.csv", SHEET, [row])
            key = dict(zip(KEY, ("P001", "pilot", "v", "c", fingerprint("AI work")), strict=True))
            write_new(root / "key.csv", KEY, [key])
            single_annotator(root / "sheet.csv", root / "gold.csv", "A", root / "key.csv", "pilot")
            gold = read(root / "gold.csv", ("annotation_method",))
            self.assertEqual(gold[0]["annotation_method"], "single_annotator")
            self.assertEqual(gold[0]["impact"], "neutral")
            self.assertNotIn("impact_b", gold[0])

    def test_report_bundle_matches_counts_and_refuses_overwrite(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            output = Path(directory) / "report.json"
            metric = metrics(
                ["positive", "negative"],
                ["positive", "positive"],
                ("positive", "negative", "mixed"),
            )
            report = {field: metric for field in ("relevance", "impact", "impact_on_gold_relevant")}
            report["disagreements"] = []
            save_report(report, output)
            rows = read(output.with_suffix(".metrics.csv"), ("tp", "fp", "fn"))
            self.assertEqual(rows[0]["tp"], "1")
            self.assertEqual(rows[0]["fp"], "1")
            self.assertEqual(rows[2]["f1"], "")
            snapshot = output.read_bytes()
            with self.assertRaises(ValueError):
                save_report(report, output)
            self.assertEqual(output.read_bytes(), snapshot)

    def source(self, root):
        rows = [
            {
                "video_id": f"v{video}",
                "comment_id": f"c{video}-{n}",
                "text_clean": f"AI work experience {video}-{n}",
            }
            for video in range(8)
            for n in range(10)
        ]
        path = root / "source.csv"
        write_new(path, ("video_id", "comment_id", "text_clean"), rows)
        return path

    def test_prepare_is_blind_video_disjoint_and_reproducible(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = self.source(root)
            for folder in ("a", "b"):
                prepare(source, root / folder, 5, 10, 42)
            keys = read(root / "a/sample_key.csv", KEY)
            pilot = {row["video_id"] for row in keys if row["split"] == "pilot"}
            evaluation = {row["video_id"] for row in keys if row["split"] == "evaluation"}
            self.assertFalse(pilot & evaluation)
            self.assertEqual(
                (root / "a/sample_key.csv").read_bytes(), (root / "b/sample_key.csv").read_bytes()
            )
            rows = read(root / "a/pilot_annotator_a.csv", SHEET)
            self.assertTrue(all(not row["relevance"] and not row["impact"] for row in rows))
            self.assertEqual(set(rows[0]), set(SHEET))
            with self.assertRaises(ValueError):
                prepare(source, root / "a", 5, 10, 42)

    def test_adjudication_keeps_disagreements_unresolved(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            first = {
                "sample_id": "E001",
                "text_clean": "AI affects work",
                "relevance": "relevant",
                "impact": "positive",
                "note": "A",
            }
            second = {**first, "impact": "negative", "note": "B"}
            write_new(root / "a.csv", SHEET, [first])
            write_new(root / "b.csv", SHEET, [second])
            agreement = adjudicate(root / "a.csv", root / "b.csv", root / "gold.csv")
            self.assertEqual(agreement["impact"], 0)
            final = read(root / "gold.csv", ("relevance", "impact"))[0]
            self.assertEqual(final["impact"], "")
            self.assertEqual(final["impact_a"], "positive")

    def test_metrics_confusion_and_undefined_values(self):
        result = metrics(
            ["positive", "negative"], ["positive", "positive"], ("positive", "negative", "mixed")
        )
        self.assertEqual(result["accuracy"], 0.5)
        self.assertEqual(result["per_class"]["positive"]["precision"], 0.5)
        self.assertEqual(result["per_class"]["negative"]["recall"], 0)
        self.assertIsNone(result["per_class"]["mixed"]["f1"])

    def test_evaluation_requires_full_text_matched_cohort(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            text = "AI saves time at work"
            key = dict(zip(KEY, ("E001", "evaluation", "v1", "c1", fingerprint(text)), strict=True))
            write_new(root / "key.csv", KEY, [key])
            gold = {
                "sample_id": "E001",
                "text_clean": text,
                "relevance": "relevant",
                "impact": "positive",
                "reviewer": "reviewer-1",
                "reviewed_at": "2026-10-15",
            }
            write_new(root / "gold.csv", tuple(gold), [gold])
            prediction = {
                "video_id": "v1",
                "comment_id": "c1",
                "text_hash": fingerprint(text),
                "model": "qwen",
                "prompt_hash": "hash",
                "relevance": "relevant",
                "impact": "positive",
            }
            write_new(root / "predictions.csv", tuple(prediction), [prediction])
            report = evaluate(
                root / "gold.csv",
                root / "key.csv",
                root / "predictions.csv",
                "qwen",
                "hash",
                "evaluation",
            )
            self.assertEqual(report["impact_on_gold_relevant"]["accuracy"], 1)
            with self.assertRaisesRegex(ValueError, "Missing predictions"):
                evaluate(
                    root / "gold.csv",
                    root / "key.csv",
                    root / "predictions.csv",
                    "other-model",
                    "hash",
                    "evaluation",
                )

    def test_incomplete_labels_cannot_become_gold(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            blank = dict(zip(SHEET, ("P001", "comment", "", "", ""), strict=True))
            write_new(root / "a.csv", SHEET, [blank])
            write_new(root / "b.csv", SHEET, [blank])
            with self.assertRaises(ValueError):
                adjudicate(root / "a.csv", root / "b.csv", root / "gold.csv")
            self.assertFalse((root / "gold.csv").exists())
