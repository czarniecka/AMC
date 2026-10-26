"""Offline tests for the CLARIN-PL client and the stage 2 classifier that uses it."""

import unittest
from unittest.mock import Mock, patch

from amc.classification import job_concern_details
from amc.classification.clarin import ClarinClient, ClarinError, json_object

LABELS = {
    "stance": "threat",
    "attitude": "negative",
    "threat_type": "hiring",
    "competence_claim": "fewer",
    "sector": "it",
}
ANSWER = (
    '{"stance": "threat", "attitude": "negative", "threat_type": "hiring", '
    '"competence_claim": "fewer", "sector": "it"}'
)


def answer(content, status=200):
    return Mock(status_code=status, json=lambda: {"choices": [{"message": {"content": content}}]})


class ClarinTests(unittest.TestCase):
    def client(self):
        return ClarinClient("token", user_agent="test", sleeper=lambda _: None)

    def test_json_is_taken_after_thinking_and_extra_text(self):
        self.assertEqual(json_object('<think>{"stance": "none"}</think> Sure: ' + ANSWER), LABELS)
        with self.assertRaises(ValueError):
            json_object("no json")

    @patch("amc.classification.clarin.requests.post")
    def test_stage2_labels_are_validated(self, post):
        classifier = job_concern_details.ClarinClassifier(self.client())
        post.return_value = answer(ANSWER)
        self.assertEqual(classifier.classify("text", "m"), LABELS)
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["messages"][0]["content"], job_concern_details.INSTRUCTION)
        self.assertEqual((body["model"], body["temperature"]), ("m", 0))
        post.return_value = answer(ANSWER.replace('"hiring"', '"none"'))
        with self.assertRaises(ValueError):
            classifier.classify("text", "m")

    @patch("amc.classification.clarin.requests.post")
    def test_rate_limit_is_retried_and_rejected_token_stops(self, post):
        post.side_effect = [Mock(status_code=429), answer("ok")]
        self.assertEqual(self.client().complete("m", "instruction", "text"), "ok")
        post.side_effect = [Mock(status_code=401)]
        with self.assertRaises(ClarinError):
            self.client().complete("m", "instruction", "text")

    def test_missing_token_is_reported(self):
        with self.assertRaises(ClarinError):
            ClarinClient(" ", user_agent="test")


if __name__ == "__main__":
    unittest.main()
