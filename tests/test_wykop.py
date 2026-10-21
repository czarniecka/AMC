"""Offline tests for Wykop privacy rules, two-stage collection and classification."""

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from amc.classification.batch_classifier import PROMPT_HASH
from amc.csv_files import read_rows
from amc.wykop import classification
from amc.wykop.collector import collect_comments, collect_entries
from amc.wykop.records import COLUMNS, RowBuilder, scrub, select_comments
from amc.wykop.selection import load_selection


class SelectionTests(unittest.TestCase):
    def test_default_settings(self):
        selection = load_selection(Path("config/wykop/collection.json"))
        self.assertEqual(len(selection.tags), 8)
        self.assertEqual(selection.start, date(2019, 1, 1))
        self.assertEqual((selection.min_upvotes, selection.first), (5, 5))

    def test_invalid_settings_are_rejected(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            path = Path(directory) / "collection.json"
            for payload in (
                '{"tags": ["#ai"], "start": "2019-01-01"}',
                '{"tags": ["ai", "ai"], "start": "2019-01-01"}',
                '{"tags": ["ai"], "start": "2019"}',
                '{"tags": ["ai"], "start": "2019-01-01", "comments": {"first": 0}}',
            ):
                path.write_text(payload, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_selection(path)


def entry(entry_id, day, tags, comments):
    return {
        "id": entry_id,
        "slug": f"s{entry_id}",
        "created_at": f"{day} 10:00:00",
        "content": f"entry {entry_id} @nick a@b.pl 600 100 200",
        "tags": tags,
        "votes": {"up": 3},
        "comments": {"count": comments},
        "author": {"username": "nick", "avatar": "x", "gender": "m"},
    }


STREAM = {
    (2022, 5): [entry(1, "2022-05-02", ["ai"], 2), entry(2, "2022-05-03", ["praca", "ai"], 0)],
    (2022, 6): [entry(3, "2022-06-02", ["praca"], 7), entry(1, "2022-05-02", ["ai"], 2)],
}
COMMENTS = {
    1: [
        {"id": 11, "content": "late", "created_at": "2022-05-02 12:00:00", "votes": {"up": 9}},
        {"id": 10, "content": "early", "created_at": "2022-05-02 11:00:00", "votes": {"up": 1}},
    ],
    3: [
        {
            "id": 30 + k,
            "content": f"c{k}",
            "created_at": f"2022-06-02 1{k}:00:00",
            "votes": {"up": 0},
        }
        for k in range(7)
    ],
}


class FakeClient:
    def __init__(self):
        self.calls = []

    def entries(self, tag, year, month):
        self.calls.append((tag, year, month))
        yield STREAM.get((year, month), []) if tag == "ai" else STREAM.get((year, month), [])[:1]

    def comments(self, entry_id):
        self.calls.append(entry_id)
        return COMMENTS.get(entry_id, [])


class RecordTests(unittest.TestCase):
    def test_masking_and_hashing(self):
        self.assertEqual(
            scrub("@janek, write a@b.pl or 600 100 200"), "@[UZYTKOWNIK], write [EMAIL] or [TEL]"
        )
        row = RowBuilder("salt").entry(entry(1, "2022-05-02", ["ai"], 2), "ai")
        self.assertEqual(len(row["author_hash"]), 64)
        self.assertNotIn("nick", str(row.values()))
        self.assertEqual((row["type"], row["created_at"]), ("entry", "2022-05-02T10:00:00"))

    def test_comment_selection(self):
        chosen = select_comments(COMMENTS[1], 5, 5)
        self.assertEqual([c["id"] for c in chosen], [11])
        self.assertEqual(
            [c["id"] for c in select_comments(COMMENTS[3], 5, 5)], [30, 31, 32, 33, 34]
        )
        self.assertEqual([c["id"] for c in select_comments(COMMENTS[1], None, 5)], [10, 11])


class CollectionTests(unittest.TestCase):
    def test_entries_then_comments_resume_without_repeats(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "wykop.csv"
            client, rows = FakeClient(), RowBuilder("salt")
            args = (client, rows, output, ["ai", "praca"], date(2022, 5, 1), date(2022, 6, 30))
            self.assertEqual(collect_entries(*args, log=lambda _: None), 3)
            self.assertEqual(collect_comments(*args, min_upvotes=5, log=lambda _: None), 6)
            client.calls.clear()
            self.assertEqual(collect_entries(*args, log=lambda _: None), 0)
            self.assertEqual(collect_comments(*args, min_upvotes=5, log=lambda _: None), 0)
            self.assertEqual(client.calls, [])
            saved = read_rows(output, COLUMNS)
            self.assertEqual(
                [r["entry_id"] for r in saved if r["type"] == "entry"], ["1", "2", "3"]
            )
            self.assertEqual(saved[0]["tag"], "ai")


class FakeClarin:
    def classify(self, text, model):
        if "bad" in text:
            raise ValueError("invalid")
        return {"relevance": "relevant", "impact": "negative"}


class ClassificationTests(unittest.TestCase):
    def test_parallel_run_resumes_and_retries_invalid(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "entries.csv"
            output = Path(directory) / "labels.csv"
            rows = RowBuilder("salt")
            with source.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(
                    stream, fieldnames=list(rows.entry(entry(1, "2022-05-02", [], 0), "ai"))
                )
                writer.writeheader()
                for n, text in enumerate(["AI took my job", "bad", "I like Python"]):
                    item = {**entry(n, "2022-05-02", [], 0), "content": text}
                    writer.writerow(rows.entry(item, "ai"))
            log = lambda _: None  # noqa: E731
            self.assertEqual(
                classification.run(FakeClarin(), source, output, "m", workers=2, log=log), 2
            )
            self.assertEqual(classification.run(FakeClarin(), source, output, "m", log=log), 0)
            self.assertEqual(classification.run(FakeClarin(), source, output, "other", log=log), 2)
            with output.open(encoding="utf-8-sig", newline="") as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(len(saved), 4)
            self.assertEqual({row["prompt_hash"] for row in saved}, {PROMPT_HASH})


if __name__ == "__main__":
    unittest.main()
