"""Offline tests for the full RepOD-format KPRM collection."""

import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from amc.jobs.client import KPRMClient
from amc.jobs.full import collect_range, missing_path
from amc.jobs.repod import COLUMNS, parse_repod, polish_date, split_head
from amc.youtube.api_client import CollectionError

PAGE = """<html><body>
<a href="/">Ogłoszenia o naborach</a>
<div>Ministerstwo Testów</div><div>00-950 Warszawa</div><div>ul. Długa</div><div>5</div>
<div>Ogłoszenie nr 157952 z dnia 1 grudnia 2025 r.</div>
<div>Poszukujemy osoby na stanowisko:</div><div>Statystyk</div>
<div>Do spraw: analiz danych</div><div>Liczba stanowisk 2</div>
<div>Wymiar etatu 1</div>
<div>Miejsce pracy ul. Długa 5, 00-950 Warszawa</div><div>Ważne do 15 grudnia 2025</div>
<div>Wynagrodzenie zasadnicze 6000 zł brutto</div>
<div>Czym będziesz się zajmować</div><ul><li>Analizuje dane</li><li>Pisze raporty</li></ul>
<div>Potrzebne ci będą (wymagania niezbędne)</div>
<ul><li>Wykształcenie: wyższe</li><li>Doświadczenie zawodowe: 1 rok</li>
<li>Kontakt: jan.kowalski@urzad.gov.pl, 600 100 200</li></ul>
<div>Dodatkowym atutem będzie (wymagania dodatkowe)</div><ul><li>Znajomość Pythona</li></ul>
<div>Co oferujemy</div><ul><li>Dofinansowanie</li></ul>
<div>Liczba odwiedzin: 42</div>
<a href="/mazowieckie/warszawa/statystyk,157952,v7.pdf">PDF</a>
</body></html>"""


class ParserTests(unittest.TestCase):
    def test_repod_fields(self):
        row = parse_repod(PAGE, "https://nabory.kprm.gov.pl/a/b/c,157952,v8", 157952)
        self.assertEqual(tuple(row), COLUMNS)
        self.assertEqual(row["ad_institution"], "Ministerstwo Testów")
        self.assertEqual(row["ad_address"], "00-950 Warszawa ul. Długa 5")
        self.assertEqual(row["ad_date_announced"], "2025-12-01")
        self.assertEqual(row["ad_job_title"], "statystyk")
        self.assertEqual(
            (row["ad_vacancies"], row["ad_work_time"], row["ad_views"]), ("2", "1", "42")
        )
        self.assertEqual(row["ad_date_valid"], "2025-12-15")
        self.assertEqual(row["ad_salary"], "6000 zł brutto")
        self.assertEqual(row["ad_responsibilities"], "Analizuje dane|-|Pisze raporty")
        self.assertEqual(row["ad_education"], "wyższe")
        self.assertEqual(
            row["ad_requirements1"], "doświadczenie zawodowe: 1 rok|-|Kontakt: [EMAIL], [TEL]"
        )
        self.assertEqual(row["ad_requirements2"], "Znajomość Pythona")
        self.assertEqual(row["template"], "v7")
        self.assertEqual(
            row["url"], "https://nabory.kprm.gov.pl/mazowieckie/warszawa/statystyk,157952,v7"
        )

    def test_dates_and_head(self):
        self.assertEqual(polish_date("01.12.2025"), "2025-12-01")
        self.assertEqual(split_head(["Urząd"]), ("Urząd", ""))


class FakeClient:
    def __init__(self):
        self.requested = []

    def find_ad(self, ad_id):
        self.requested.append(ad_id)
        if ad_id == 3:
            raise CollectionError("timeout")
        return None if ad_id == 2 else (PAGE.replace("157952", str(ad_id)), f"https://x/{ad_id}")


class CollectionTests(unittest.TestCase):
    def test_resume_skips_saved_and_missing_but_retries_errors(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "kprm.csv"
            client = FakeClient()
            self.assertEqual(collect_range(client, output, range(1, 5), log=lambda _: None), 2)
            self.assertEqual(missing_path(output).read_text().split(), ["2"])
            client.requested.clear()
            self.assertEqual(collect_range(client, output, range(1, 5), log=lambda _: None), 0)
            self.assertEqual(client.requested, [3])
            with output.open(encoding="utf-8-sig", newline="") as stream:
                self.assertEqual([r["ad_id"] for r in csv.DictReader(stream)], ["1", "4"])

    def test_client_falls_back_to_other_templates(self):
        session = Mock(headers={})
        session.get.side_effect = [
            Mock(status_code=404),
            Mock(status_code=200, text="<p>Ogłoszenie nr 5</p>", url="https://x/v7"),
            Mock(status_code=200, text="<p>Ogłoszenie nr 6</p>", url="https://x/v7b"),
        ]
        client = KPRMClient(None, session=session, sleeper=lambda _: None)
        self.assertEqual(client.find_ad(5)[1], "https://x/v7")
        self.assertEqual(client.find_ad(6)[1], "https://x/v7b")
        urls = [call.args[0] for call in session.get.call_args_list]
        self.assertEqual([url.rsplit(",", 1)[-1] for url in urls], ["v8", "v7", "v7"])


if __name__ == "__main__":
    unittest.main()
