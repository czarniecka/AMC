"""Offline checks for the screening runner: validation, retries, resume and merge."""

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from amc.youtube.screening_run import label_batch, merge, run, validate_response

INSTRUCTION = "Classify each comment."
PROMPT_HASH = hashlib.sha256(INSTRUCTION.encode()).hexdigest()


def batch(batch_id: str, count: int, start: int = 1) -> dict:
    return {
        "batch_id": batch_id,
        "comments": [{"id": f"c{start + i:03d}", "text": f"text {i}"} for i in range(count)],
    }


def answer(source: dict, h1: str = "yes", concern: str = "no") -> dict:
    return {
        "batch_id": source["batch_id"],
        "labels": [
            {"id": c["id"], "h1_related": h1, "job_security_concern": concern}
            for c in source["comments"]
        ],
    }


def prepare_directory(root: Path, batches: list[dict]) -> None:
    (root / "screening_config.json").write_text(
        json.dumps({"instruction": INSTRUCTION}), encoding="utf-8"
    )
    (root / "batches.jsonl").write_text(
        "".join(json.dumps(item) + "\n" for item in batches), encoding="utf-8"
    )
    with (root / "manifest.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=(
                "item_id",
                "batch_id",
                "video_id",
                "comment_id",
                "published_at",
                "period",
                "text_hash",
            ),
        )
        writer.writeheader()
        for item in batches:
            for comment in item["comments"]:
                writer.writerow(
                    {
                        "item_id": comment["id"],
                        "batch_id": item["batch_id"],
                        "video_id": "v",
                        "comment_id": "x",
                        "published_at": "2023-01-01T00:00:00Z",
                        "period": "post",
                        "text_hash": "h",
                    }
                )


class ValidateResponseTests(unittest.TestCase):
    def test_valid_answer_maps_every_id(self):
        source = batch("b1", 3)
        self.assertEqual(set(validate_response(source, answer(source))), {"c001", "c002", "c003"})

    def test_rejects_wrong_batch_id_missing_duplicate_and_unknown_ids(self):
        source = batch("b1", 2)
        wrong = {**answer(source), "batch_id": "b2"}
        missing = {**answer(source), "labels": answer(source)["labels"][:1]}
        duplicate = {**answer(source), "labels": answer(source)["labels"] * 2}
        unknown = answer(batch("b1", 2, start=50))
        for payload in (wrong, missing, duplicate, unknown):
            with self.assertRaises(ValueError):
                validate_response(source, payload)

    def test_rejects_bad_value_extra_field_and_unrelated_with_concern(self):
        source = batch("b1", 1)
        for payload in (
            answer(source, h1="maybe"),
            answer(source, h1="no", concern="yes"),
            {**answer(source), "labels": [{**answer(source)["labels"][0], "note": "x"}]},
            "not an object",
        ):
            with self.assertRaises(ValueError):
                validate_response(source, payload)


class LabelBatchTests(unittest.TestCase):
    def test_retries_then_succeeds(self):
        source = batch("b1", 2)
        calls = []

        def ask(instruction, message):
            calls.append(1)
            return {"batch_id": "b1", "labels": []} if len(calls) < 3 else answer(source)

        labels, attempts = label_batch(source, INSTRUCTION, ask, max_retries=3, min_split=1)
        self.assertEqual((len(labels), attempts), (2, 3))

    def test_failing_batch_is_split_in_halves(self):
        source = batch("b1", 4)

        def ask(instruction, message):
            received = json.loads(message)
            if len(received["comments"]) > 2:
                raise ValueError("too long")
            return answer(received)

        labels, attempts = label_batch(source, INSTRUCTION, ask, max_retries=2, min_split=2)
        self.assertEqual(set(labels), {"c001", "c002", "c003", "c004"})
        self.assertEqual(attempts, 2 + 1 + 1)

    def test_gives_up_at_the_smallest_split(self):
        with self.assertRaises(ValueError):
            label_batch(
                batch("b1", 2),
                INSTRUCTION,
                lambda instruction, message: {"batch_id": "b1", "labels": []},
                max_retries=2,
                min_split=2,
            )


class RunTests(unittest.TestCase):
    def test_run_resumes_and_merge_joins_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batches = [batch("b1", 2, 1), batch("b2", 2, 3), batch("b3", 1, 5)]
            prepare_directory(root, batches)
            seen = []

            def ask(instruction, message):
                received = json.loads(message)
                seen.append(received["batch_id"])
                return answer(received)

            first = run(root, ask, "m1", limit=2, log=lambda message: None)
            self.assertEqual(first, {"labeled": 2, "failed": 0, "pending": 1})
            second = run(root, ask, "m1", log=lambda message: None)
            self.assertEqual(second, {"labeled": 1, "failed": 0, "pending": 0})
            self.assertEqual(seen, ["b1", "b2", "b3"])
            counts = merge(root)
            self.assertEqual(counts, {"manifest": 5, "labeled": 5, "missing": 0})
            with (root / "labels.csv").open(encoding="utf-8-sig", newline="") as stream:
                rows = list(csv.DictReader(stream))
            self.assertEqual(rows[0]["prompt_sha256"], PROMPT_HASH)
            self.assertEqual(rows[0]["h1_related"], "yes")

    def test_other_model_or_instruction_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_directory(root, [batch("b1", 1)])
            run(root, lambda i, m: answer(json.loads(m)), "m1", log=lambda message: None)
            with self.assertRaises(ValueError):
                run(root, lambda i, m: answer(json.loads(m)), "m2", log=lambda message: None)

    def test_failed_batch_is_recorded_and_left_unlabeled(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prepare_directory(root, [batch("b1", 1)])
            counts = run(
                root,
                lambda instruction, message: "garbage",
                "m1",
                max_retries=1,
                min_split=1,
                log=lambda message: None,
            )
            self.assertEqual(counts, {"labeled": 0, "failed": 1, "pending": 0})
            self.assertTrue((root / "failures.jsonl").exists())
            self.assertEqual(merge(root)["missing"], 1)


if __name__ == "__main__":
    unittest.main()
