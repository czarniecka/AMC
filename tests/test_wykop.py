"""Offline tests for Wykop privacy rules, two-stage collection and classification."""

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from amc.classification import job_concern, job_concern_details
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


class FakeOllama:
    def classify(self, text, model):
        if "bad" in text:
            raise ValueError("invalid")
        return {"ai": "yes", "work": "no"}


class JobConcernTests(unittest.TestCase):
    @patch("amc.classification.job_concern.ask")
    def test_labels_are_validated(self, ask):
        ask.return_value = {"ai": "yes", "work": "no"}
        self.assertEqual(job_concern.OllamaClient().classify("t", "m"), ask.return_value)
        self.assertIs(ask.call_args.args[2], job_concern.INSTRUCTION)
        for labels in (
            {"ai": "yes", "work": "yes", "stance": "threat"},
            {"ai": "yes", "work": "maybe"},
            {"ai": "yes"},
        ):
            ask.return_value = labels
            with self.assertRaises(ValueError):
                job_concern.OllamaClient().classify("t", "m")


class JobConcernDetailsTests(unittest.TestCase):
    LABELS = {
        "stance": "threat",
        "attitude": "negative",
        "threat_type": "hiring",
        "competence_claim": "fewer",
        "sector": "it",
    }

    @patch("amc.classification.job_concern_details.ask")
    def test_threat_type_follows_stance(self, ask):
        client = job_concern_details.OllamaClient()
        ask.return_value = self.LABELS
        self.assertEqual(client.classify("AI", "m"), self.LABELS)
        self.assertEqual(ask.call_args.args[0], "AI")
        self.assertIs(ask.call_args.args[2], job_concern_details.INSTRUCTION)
        ask.return_value = {**self.LABELS, "stance": "opportunity", "threat_type": "none"}
        self.assertEqual(client.classify("AI", "m")["threat_type"], "")
        for labels in (
            {**self.LABELS, "threat_type": "none"},
            {**self.LABELS, "stance": "none"},
            {**self.LABELS, "stance": "fear"},
            {**self.LABELS, "sector": "medicine"},
            {key: self.LABELS[key] for key in ("stance", "attitude", "sector")},
        ):
            ask.return_value = labels
            with self.assertRaises(ValueError):
                client.classify("AI", "m")


class ClassificationTests(unittest.TestCase):
    def test_mirko_anonim_header_and_footer_are_removed(self):
        text = (
            "✨️ **Tytuł od AI** [Ⓘ](https://mirko.pro/mirko-anonim/faq#wsparcie-ai)\n"
            "Szukam pracy od roku.\n· Ma 2 punkty\n\n─────\n"
            "· Akcje: [Odpowiedz](https://mirko.pro/x)\n"
            "!Pomóż [❤️ tutaj](https://buycoffee.to/mirko.pro)."
        )
        self.assertEqual(classification.model_text(text), "Szukam pracy od roku.")
        self.assertEqual(classification.model_text("· AI · praca"), "· AI · praca")

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
                classification.run(FakeOllama(), source, output, "m", workers=2, log=log), 2
            )
            self.assertEqual(classification.run(FakeOllama(), source, output, "m", log=log), 0)
            self.assertEqual(classification.run(FakeOllama(), source, output, "other", log=log), 2)
            with output.open(encoding="utf-8-sig", newline="") as stream:
                saved = list(csv.DictReader(stream))
            self.assertEqual(len(saved), 4)
            self.assertEqual({row["prompt_hash"] for row in saved}, {job_concern.PROMPT_HASH})
            self.assertEqual({(row["ai"], row["work"]) for row in saved}, {("yes", "no")})
            joined, stale = classification.labeled(source, output, "m")
            self.assertEqual((len(joined), stale), (2, 0))
            self.assertEqual(tuple(joined[0]), classification.LABELED_COLUMNS)
            self.assertEqual({row["text"] for row in joined}, {"AI took my job", "I like Python"})

    def test_stage2_reads_an_export_with_extra_columns(self):
        labels = {**JobConcernDetailsTests.LABELS}

        class Fake:
            def classify(self, text, model):
                return labels

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "ai_work.csv"
            output = Path(directory) / "stage2.csv"
            with source.open("w", encoding="utf-8-sig", newline="") as stream:
                writer = csv.DictWriter(stream, fieldnames=[*COLUMNS, "ai", "work", "stance"])
                writer.writeheader()
                row = RowBuilder("salt").entry(entry(1, "2024-05-02", [], 0), "ai")
                writer.writerow({**row, "ai": "yes", "work": "yes", "stance": "none"})
            args = (Fake(), source, output, "deepseek")
            options = {
                "columns": classification.STAGE2_COLUMNS,
                "prompt_hash": job_concern_details.PROMPT_HASH,
                "log": lambda _: None,
            }
            self.assertEqual(classification.run(*args, **options), 1)
            self.assertEqual(classification.run(*args, **options), 0)
            saved = read_rows(output, classification.STAGE2_COLUMNS)
            self.assertEqual({key: saved[0][key] for key in labels}, labels)
            self.assertEqual(saved[0]["prompt_hash"], job_concern_details.PROMPT_HASH)


if __name__ == "__main__":
    unittest.main()
