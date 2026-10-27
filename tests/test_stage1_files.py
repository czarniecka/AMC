"""Offline checks for the stage 1 input export and the merge with the manifest."""

import csv
import json
import tempfile
import unittest
from pathlib import Path

from amc.youtube.stage1_files import export_input, merge_output


def prepare(root: Path) -> None:
    batches = [
        {"batch_id": "b00001", "comments": [{"id": "c1", "text": "AI took my job"}]},
        {"batch_id": "b00002", "comments": [{"id": "c2", "text": "nice video\nthanks"}]},
    ]
    (root / "batches.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in batches), encoding="utf-8"
    )
    with (root / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["item_id", "batch_id", "video_id", "comment_id", "published_at", "period", "text_hash"]
        )
        writer.writerow(["c1", "b00001", "v1", "real1", "2023-01-01T00:00:00Z", "post", "h1"])
        writer.writerow(["c2", "b00002", "v2", "real2", "2021-01-01T00:00:00Z", "pre", "h2"])


def classified(root: Path, rows: list[dict]) -> None:
    columns = ["type", "entry_id", "text_hash", "ai", "work", "model", "prompt_hash"]
    with (root / "stage1_output.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def row(entry_id: str, ai: str, work: str, model: str = "m", prompt: str = "p") -> dict:
    return {
        "type": "youtube",
        "entry_id": entry_id,
        "text_hash": "x",
        "ai": ai,
        "work": work,
        "model": model,
        "prompt_hash": prompt,
    }


class Stage1FilesTests(unittest.TestCase):
    def test_export_uses_short_ids_and_keeps_text(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root)
            self.assertEqual(export_input(root), 2)
            with (root / "stage1_input.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual([r["entry_id"] for r in rows], ["c1", "c2"])
            self.assertEqual(rows[1]["text"], "nice video\nthanks")
            self.assertNotIn("real1", (root / "stage1_input.csv").read_text(encoding="utf-8"))
            with self.assertRaises(ValueError):
                export_input(root)

    def test_merge_adds_period_and_reports_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root)
            classified(root, [row("c1", "yes", "yes")])
            counts = merge_output(root)
            self.assertEqual(counts, {"manifest": 2, "labeled": 1, "missing": 1})
            with (root / "stage1_labels.csv").open(encoding="utf-8-sig", newline="") as stream:
                merged = list(csv.DictReader(stream))
            self.assertEqual(
                (merged[0]["period"], merged[0]["ai"], merged[0]["work"]), ("post", "yes", "yes")
            )

    def test_merge_refuses_mixed_versions_unless_selected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare(root)
            classified(root, [row("c1", "yes", "yes", "m1"), row("c2", "no", "no", "m2")])
            with self.assertRaises(ValueError):
                merge_output(root)
            self.assertEqual(merge_output(root, model="m2")["labeled"], 1)


if __name__ == "__main__":
    unittest.main()
