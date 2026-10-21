"""Offline tests for Hacker News header parsing and resumable thread collection."""

import csv
import tempfile
import unittest
from pathlib import Path

from amc.hn.collector import Thread, collect, find_threads, month_start, thread_ads
from amc.hn.parser import COLUMNS, paragraphs, parse_header, scrub


class ParserTests(unittest.TestCase):
    def test_header_fields(self):
        fields = parse_header("Acme | Senior Backend Engineer | Berlin, Germany | REMOTE | $150k")
        self.assertEqual(fields["company"], "Acme")
        self.assertEqual(fields["role"], "Senior Backend Engineer")
        self.assertEqual(fields["location"], "Berlin, Germany")
        self.assertEqual(fields["remote"], "yes")
        self.assertEqual(fields["salary"], "$150k")

    def test_onsite_and_work_mode_only_parts(self):
        fields = parse_header("DRW | Chicago, IL | Onsite | Full-Time | drw.com")
        self.assertEqual(
            (fields["location"], fields["role"], fields["remote"]), ("Chicago, IL", "", "no")
        )

    def test_header_without_pipes_is_not_guessed(self):
        fields = parse_header("FreeAgent, Edinburgh and REMOTE")
        self.assertEqual((fields["company"], fields["location"], fields["remote"]), ("", "", "yes"))

    def test_paragraphs_keep_links_and_mask_contacts(self):
        html = (
            'Acme | Dev | <a href="https:&#x2F;&#x2F;acme.io">acme.io</a>'
            "<p>Write to jobs [at] acme [dot] io"
        )
        self.assertEqual(paragraphs(html), ["Acme | Dev | https://acme.io", "Write to [EMAIL]"])
        self.assertEqual(scrub("call (415) 555-1234 or x@y.io"), "call [TEL] or [EMAIL]")

    def test_month_start_wraps_year(self):
        self.assertEqual(month_start("2019-12", 1), month_start("2020-01"))


class FakeClient:
    """Thread 1 with kids 10 (in the tree), 11 (deleted) and 12 (only in Firebase)."""

    def __init__(self):
        self.calls = []

    def threads(self, start, end):
        return [
            {
                "objectID": "1",
                "title": "Ask HN: Who is hiring? (January 2019)",
                "created_at_i": 100,
            },
            {
                "objectID": "2",
                "title": "Ask HN: Who wants to be hired? (January 2019)",
                "created_at_i": 100,
            },
        ]

    def item(self, item_id):
        self.calls.append(item_id)
        return {
            1: {"kids": [10, 11, 12]},
            11: {"deleted": True},
            12: {"time": 300, "text": "Beta | QA Tester | Remote"},
        }.get(item_id)

    def tree(self, item_id):
        self.calls.append(f"tree {item_id}")
        return {"children": [{"id": 10, "created_at_i": 200, "text": "Acme | Dev | NYC<p>Body"}]}


class CollectorTests(unittest.TestCase):
    def test_only_hiring_threads_with_month_from_title(self):
        self.assertEqual(
            find_threads(FakeClient(), "2019-01", "2019-01"), [Thread(1, "2019-01", 100)]
        )

    def test_deleted_comments_are_skipped(self):
        rows, skipped = thread_ads(FakeClient(), Thread(1, "2019-01", 100))
        self.assertEqual([row["ad_id"] for row in rows], [10, 12])
        self.assertEqual(skipped, 1)
        self.assertEqual(rows[0]["ad_text"], "Acme | Dev | NYC\n\nBody")

    def test_finished_threads_are_not_fetched_again(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "hn.csv"
            client = FakeClient()
            self.assertEqual(collect(client, output, "2019-01", "2019-01", log=lambda _: None), 2)
            client.calls.clear()
            self.assertEqual(collect(client, output, "2019-01", "2019-01", log=lambda _: None), 0)
            self.assertEqual(client.calls, [])
            with output.open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(tuple(reader.fieldnames), COLUMNS)
                self.assertEqual(len(list(reader)), 2)


if __name__ == "__main__":
    unittest.main()
