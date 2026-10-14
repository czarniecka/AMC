"""Offline tests for fragment splitting and balanced drawing."""

import unittest

from amc.jobs.fragments import Fragment, draw_fragments, split_line


class SplitTests(unittest.TestCase):
    def test_lead_in_and_separators(self):
        lead, parts = split_line("Znajomość: ustawy o finansach, Kodeksu cywilnego; Prawa pracy")
        self.assertEqual(lead, "Znajomość")
        self.assertEqual(parts, ["ustawy o finansach", "Kodeksu cywilnego", "Prawa pracy"])

    def test_decimal_comma_and_trailing_comma_are_kept_clean(self):
        self.assertEqual(split_line("Staż 1,5 roku,")[1], ["Staż 1,5 roku"])

    def test_late_colon_is_not_a_lead_in(self):
        line = "Doświadczenie zawodowe co najmniej 1 rok w obszarze administracji publicznej: praca"
        self.assertEqual(split_line(line)[0], "")

    def test_full_text_prepends_lead(self):
        self.assertEqual(
            Fragment(1, "pre", "l", "ustawy", "Znajomość").full_text, "Znajomość: ustawy"
        )


class DrawTests(unittest.TestCase):
    def pool(self):
        return [
            Fragment(ad, period, "line", f"fragment {ad} {i}")
            for period in ("pre", "post")
            for ad in range(10)
            for i in range(6)
        ]

    def test_balanced_deterministic_and_capped_per_ad(self):
        first = draw_fragments(self.pool(), 12, 2, seed=3)
        self.assertEqual(first, draw_fragments(self.pool(), 12, 2, seed=3))
        self.assertEqual([f.period for f in first].count("pre"), 12)
        self.assertEqual([f.period for f in first].count("post"), 12)
        for period in ("pre", "post"):
            ads = [f.ad_id for f in first if f.period == period]
            self.assertLessEqual(max(ads.count(a) for a in set(ads)), 2)


if __name__ == "__main__":
    unittest.main()
