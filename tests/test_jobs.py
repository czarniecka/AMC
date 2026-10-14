"""Offline tests for advertisement parsing, sampling and resumable collection."""

import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock

from amc.jobs import sampling
from amc.jobs.client import KPRMClient
from amc.jobs.collector import build_sample, collect
from amc.jobs.parser import ParseError, parse_ad
from amc.jobs.sampling import Window, draw, first_id_on_or_after
from amc.jobs.storage import JobStore

UNIT = "job-post__main-content__job-information__important-information__job-title__institution-unit"


SALARY = (
    '<div class="info-circle__content info-circle__content--salary '
    'info-circle__content--small-text"> 5000 zł brutto </div>'
)


def ad_page(
    ad_id: int,
    published: str = "02.05.2023",
    required: str = "<li>Wykształcenie: wyższe</li>",
    salary: str = SALARY,
):
    return f"""<html><div class="job-post__header__bottom-row__office-data__office-name">
  Urząd Testowy </div><address>
    <span>00-001</span>
    <span>Warszawa</span>
  </address>
  <span class="adv-number">{ad_id}</span>
  </span>
  / {published}
  <h1 class="x">analityk/analityczka</h1>
  <span class="{UNIT}">
    w Wydziale Danych</span>
  <div class="info-circle__content info-circle__content--work-time-cnt">2</div>
  <div class="info-circle__content info-circle__content--work-time">1</div>
  <div class="info-circle__content info-circle__content--small-text info-circle__content--valid-to">
    <span> 23 </span> <span> października </span> <br> <span> 2026 r. </span></div>
  {salary}
  Nabór zakończony
  <div class="job-post__main-content__responsibilities customize-bar expandable-section">
    <div class="bar__text">Czym będziesz się zajmować</div>
    <ul><li>Analizuje dane z użyciem narzędzi AI,</li><li>Przygotowuje raporty</li></ul></div>
  <div class="job-post__main-content__requirements customize-bar expandable-section">
    <div class="bar__text">Kogo poszukujemy</div>
    <div class="necessary-requirements"><div class="warning-b">Potrzebne ci będą
      <small>(wymagania niezbędne)</small></div></div>
    <ul>{required}<li>Nieskazanie za umyślne
      przestępstwo skarbowe</li></ul>
    <div class="job-post__main-content__requirements__list__additional-requirements">
      <div class="warning-b">Dodatkowym atutem będzie
        <small>(wymagania dodatkowe)</small></div></div>
    <ul><li>Znajomość Pythona</li></ul></div>
  <div class="job-post__main-content__our-offer customize-bar expandable-section">Oferta</div>
</html>"""


class ParserTests(unittest.TestCase):
    def test_extracts_metadata_and_sections(self):
        ad, text = parse_ad(ad_page(120000))
        self.assertEqual(ad.ad_id, 120000)
        self.assertEqual(ad.published_at, "2023-05-02")
        self.assertEqual(ad.valid_until, "2026-10-23")
        self.assertEqual(
            (ad.institution, ad.city, ad.title),
            ("Urząd Testowy", "Warszawa", "analityk/analityczka"),
        )
        self.assertEqual((ad.positions, ad.work_time, ad.salary_text), ("2", "1", "5000 zł brutto"))
        self.assertEqual(text.tasks, "Analizuje dane z użyciem narzędzi AI,\nPrzygotowuje raporty")
        self.assertEqual(
            text.requirements_required,
            "Wykształcenie: wyższe\nNieskazanie za umyślne przestępstwo skarbowe",
        )
        self.assertEqual(text.requirements_optional, "Znajomość Pythona")
        self.assertNotIn("Oferta", text.requirements_optional)

    def test_missing_salary_is_empty_but_deadline_is_kept(self):
        ad, _ = parse_ad(ad_page(1, salary=""))
        self.assertEqual((ad.salary_text, ad.valid_until), ("", "2026-10-23"))

    def test_error_page_is_rejected(self):
        with self.assertRaises(ParseError):
            parse_ad("<html><title>Błąd (#8)</title></html>")


class FakeClient:
    """Serves IDs published at 20 per day starting 2021-01-01, with a gap of missing IDs."""

    def __init__(self):
        self.request_count = 0

    def fetch_ad(self, ad_id):
        self.request_count += 1
        if 100 <= ad_id % 1000 < 105:
            return None
        day = date(2021, 1, 1) + timedelta(days=ad_id // 20 - 3500)
        return ad_page(ad_id, day.strftime("%d.%m.%Y"))


class SamplingTests(unittest.TestCase):
    def test_boundary_search_finds_first_id_of_day(self):
        client = FakeClient()
        original = sampling.ANCHORS
        sampling.ANCHORS = ()
        try:
            target = date(2021, 7, 1)
            found = first_id_on_or_after(client, target)
        finally:
            sampling.ANCHORS = original
        expected = (3500 + (target - date(2021, 1, 1)).days) * 20
        self.assertEqual(found, expected)

    def test_draw_is_deterministic_and_bounded(self):
        self.assertEqual(draw(range(1000, 2000), 10, 7), draw(range(1000, 2000), 10, 7))
        self.assertEqual(len(draw(range(5), 10, 1)), 5)


class CollectionTests(unittest.TestCase):
    def test_client_caches_pages_and_treats_500_as_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            session = Mock(headers={})
            session.get.side_effect = [
                Mock(status_code=200, text="<html>ok</html>"),
                Mock(status_code=500, text="Błąd"),
            ]
            client = KPRMClient(Path(directory), session=session, sleeper=lambda _: None)
            self.assertEqual(client.fetch_ad(1), "<html>ok</html>")
            self.assertEqual(client.fetch_ad(1), "<html>ok</html>")
            self.assertIsNone(client.fetch_ad(2))
            self.assertEqual(session.get.call_count, 2)

    def test_collect_resumes_and_marks_missing(self):
        window = Window("w", date(2021, 1, 1), date(2021, 1, 2))
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient()
            store = JobStore(Path(directory))
            store.sample = []
            from amc.jobs.storage import SampleItem

            store.sample = [SampleItem(i, window.name) for i in (99, 100, 120, 121)]
            collect(store, client, limit=2, log=lambda _: None)
            store.close()
            store = JobStore(Path(directory))
            try:
                self.assertEqual(
                    [i.status for i in store.sample], ["ok", "missing", "pending", "pending"]
                )
                collect(store, client, log=lambda _: None)
            finally:
                store.close()
            store = JobStore(Path(directory))
            try:
                self.assertEqual(sorted(store.ads), [99, 120, 121])
                self.assertEqual(store.texts[99].requirements_optional, "Znajomość Pythona")
            finally:
                store.close()

    def test_build_sample_does_not_redraw_existing_windows(self):
        window = Window("w", date(2021, 1, 1), date(2021, 1, 1))
        with tempfile.TemporaryDirectory() as directory:
            store = JobStore(Path(directory))
            try:
                from amc.jobs.storage import SampleItem

                store.sample = [SampleItem(1, "w")]
                build_sample(store, FakeClient(), [window], 5, 1, log=lambda _: None)
                self.assertEqual([i.ad_id for i in store.sample], [1])
            finally:
                store.close()


if __name__ == "__main__":
    unittest.main()
