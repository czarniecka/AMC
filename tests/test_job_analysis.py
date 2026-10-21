"""Offline tests for codebook flags and small-sample statistics."""

import unittest
from pathlib import Path

from amc.jobs.analysis import (
    Codebook,
    bootstrap_ci,
    fisher_exact,
    flag_ad,
    fragment_decision,
    holm,
    institution_group,
    period_of,
    permutation_test,
)

CODEBOOK = Codebook.load(Path(__file__).resolve().parents[1] / "config/jobs/skill_codebook.json")


class FlagTests(unittest.TestCase):
    def test_boilerplate_and_formal_lines_are_excluded(self):
        required = "\n".join(
            [
                "Wykształcenie: wyższe",
                "Posiadanie obywatelstwa polskiego",
                "Nieskazanie za umyślne przestępstwo skarbowe",
                "Prawo jazdy kat. B",
                "Umiejętność pracy w zespole",
            ]
        )
        count, found = flag_ad(CODEBOOK, required, "")
        self.assertEqual((count, found), (1, frozenset({"teamwork"})))

    def test_categories_come_from_required_and_optional_lines(self):
        count, found = flag_ad(
            CODEBOOK,
            "Znajomość obsługi komputera\nUmiejętność analitycznego myślenia",
            "Znajomość narzędzi AI, np. ChatGPT",
        )
        self.assertEqual(count, 3)
        self.assertEqual(found, {"digital_basic", "analytical_thinking", "ai_automation"})

    def test_categories_are_per_fragment_not_per_line(self):
        # "Komunikatywność" must not be credited to a line only because a sibling fragment
        # names teamwork; each fragment is judged on its own text.
        line = "Umiejętności: praca w zespole, obsługa komputera"
        self.assertEqual(
            fragment_decision(CODEBOOK, line, "Umiejętności: praca w zespole"),
            ("skill", frozenset({"teamwork"})),
        )
        self.assertEqual(
            fragment_decision(CODEBOOK, line, "obsługa komputera"),
            ("skill", frozenset({"digital_basic"})),
        )
        _, found = flag_ad(CODEBOOK, line, "")
        self.assertEqual(found, {"teamwork", "digital_basic"})

    def test_formal_filter_uses_the_whole_line(self):
        self.assertEqual(
            fragment_decision(CODEBOOK, "Wykształcenie: wyższe weterynaryjne", "wyższe")[0],
            "formal",
        )

    def test_statistics_is_data_analysis_not_analytical_thinking(self):
        _, found = flag_ad(CODEBOOK, "Umiejętność analizy wyników badań statystycznych", "")
        self.assertEqual(found, {"data_analysis"})

    def test_period_and_group(self):
        self.assertEqual((period_of("2022-12-31"), period_of("2023-01-01")), ("pre", "post"))
        self.assertEqual(institution_group("Powiatowy Inspektorat Weterynarii", ""), "veterinary")
        self.assertEqual(institution_group("Urząd Gminy", ""), "other")


class StatisticsTests(unittest.TestCase):
    def test_fisher_matches_known_value(self):
        # Classic tea-tasting table: p = 0.4857 (two-sided).
        self.assertAlmostEqual(fisher_exact(3, 1, 1, 3), 0.4857, places=3)
        self.assertEqual(fisher_exact(5, 5, 5, 5), 1.0)

    def test_holm_is_monotone_and_capped(self):
        adjusted = holm({"a": 0.01, "b": 0.02, "c": 0.5})
        self.assertAlmostEqual(adjusted["a"], 0.03)
        self.assertAlmostEqual(adjusted["b"], 0.04)
        self.assertEqual(adjusted["c"], 0.5)

    def test_permutation_detects_shift_and_ignores_noise(self):
        labels = ["pre"] * 20 + ["post"] * 20
        strata = ["all"] * 40
        shifted = [1.0] * 20 + [5.0] * 20
        self.assertLess(permutation_test(shifted, labels, strata, iterations=500), 0.01)
        flat = [1.0, 2.0] * 20
        self.assertGreater(permutation_test(flat, labels, strata, iterations=500), 0.5)

    def test_bootstrap_interval_contains_true_shift(self):
        low, high = bootstrap_ci([1.0, 2.0, 3.0] * 10, [2.0, 3.0, 4.0] * 10, iterations=500)
        self.assertLess(low, 1.0)
        self.assertGreater(high, 1.0)


if __name__ == "__main__":
    unittest.main()
