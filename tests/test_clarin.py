"""Offline tests for the CLARIN-PL backend sharing the Ollama classifier's validation."""

import unittest
from unittest.mock import Mock, patch

from amc.classification.clarin import ClarinClient, ClarinError


def answer(content, status=200):
    return Mock(status_code=status, json=lambda: {"choices": [{"message": {"content": content}}]})


class ClarinTests(unittest.TestCase):
    def client(self):
        return ClarinClient("token", user_agent="test", sleeper=lambda _: None)

    @patch("amc.classification.clarin.requests.post")
    def test_labels_are_extracted_and_validated(self, post):
        post.return_value = answer('Sure: {"relevance": "relevant", "impact": "mixed"}')
        self.assertEqual(
            self.client().classify("text", "m"), {"relevance": "relevant", "impact": "mixed"}
        )
        post.return_value = answer('{"relevance": "unrelated", "impact": "negative"}')
        with self.assertRaises(ValueError):
            self.client().classify("text", "m")
        post.return_value = answer("no json")
        with self.assertRaises(ValueError):
            self.client().classify("text", "m")

    @patch("amc.classification.clarin.requests.post")
    def test_rate_limit_is_retried_and_rejected_token_stops(self, post):
        post.side_effect = [
            Mock(status_code=429),
            answer('{"relevance": "unclear", "impact": "unclear"}'),
        ]
        self.assertEqual(self.client().classify("text", "m")["relevance"], "unclear")
        post.side_effect = [Mock(status_code=401)]
        with self.assertRaises(ClarinError):
            self.client().classify("text", "m")

    def test_missing_token_is_reported(self):
        with self.assertRaises(ClarinError):
            ClarinClient(" ", user_agent="test")


if __name__ == "__main__":
    unittest.main()
