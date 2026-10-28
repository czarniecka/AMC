"""Check the rules that keep strong-model labels usable for H1."""

import unittest

from scripts.youtube.import_strong_review import validate_answer
from scripts.youtube.prepare_strong_review import bucket, instruction


def label(**changes):
    value = {
        "id": "c1",
        "ai": "no",
        "work": "yes",
        "stance": "none",
        "job_insecurity": "yes",
        "attitude": None,
        "threat_type": None,
        "competence_claim": None,
        "sector": None,
    }
    value.update(changes)
    return {"batch_id": "review_0001", "labels": [value]}


class StrongReviewValidationTests(unittest.TestCase):
    def test_prompt_contains_codebook_without_wykop_methods(self):
        prompt = instruction()
        self.assertIn("## `threat_type`", prompt)
        self.assertIn("job_insecurity", prompt)
        self.assertIn("## Specyfika YouTube'a", prompt)
        self.assertNotIn("Qwen3 8B", prompt)
        self.assertNotIn("Mirko Anonim", prompt)

    def test_ai_without_work_is_its_own_selection_bucket(self):
        self.assertEqual(bucket({"ai": "yes", "work": "no", "stance": "none"}), "ai_only")

    def test_work_concern_without_ai_is_retained(self):
        answer = label()
        self.assertEqual(validate_answer(answer, "review_0001", ["c1"]), answer["labels"])

    def test_ai_work_threat_requires_deep_labels(self):
        answer = label(
            ai="yes",
            stance="threat",
            attitude="negative",
            threat_type="job_loss",
            competence_claim="none",
            sector="unspecified",
        )
        self.assertEqual(validate_answer(answer, "review_0001", ["c1"]), answer["labels"])
        answer["labels"][0]["threat_type"] = None
        with self.assertRaisesRegex(ValueError, "Missing threat_type"):
            validate_answer(answer, "review_0001", ["c1"])

    def test_rejects_incomplete_or_misaligned_batch(self):
        with self.assertRaisesRegex(ValueError, "Missing or extra"):
            validate_answer(label(), "review_0001", ["c1", "c2"])
        with self.assertRaisesRegex(ValueError, "order or ID"):
            validate_answer(label(), "review_0001", ["other"])


if __name__ == "__main__":
    unittest.main()
