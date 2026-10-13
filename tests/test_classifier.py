"""Validate local classification output and request controls without a model."""

import unittest
from unittest.mock import MagicMock, patch

from amc.classification.classifier import classify


class ClassifierTests(unittest.TestCase):
    @patch("amc.classification.classifier.requests.Session")
    def test_unrelated_positive_combination_is_rejected(self, factory):
        session = factory.return_value.__enter__.return_value
        session.post.return_value.json.return_value = {
            "message": {"content": '{"relevance":"unrelated","impact":"positive"}'}
        }
        with self.assertRaisesRegex(ValueError, "Unrelated"):
            classify("Thanks for the video", "qwen3:8b")

    @patch("amc.classification.classifier.requests.Session")
    def test_local_request_disables_thinking_and_validates_labels(self, factory):
        session = MagicMock()
        factory.return_value.__enter__.return_value = session
        session.post.return_value.json.return_value = {
            "message": {"content": '{"relevance":"relevant","impact":"mixed"}'}
        }
        self.assertEqual(classify("AI helps but adds pressure", "qwen3:8b")["impact"], "mixed")
        self.assertFalse(session.trust_env)
        args, kwargs = session.post.call_args
        self.assertEqual(args[0], "http://127.0.0.1:11434/api/chat")
        self.assertFalse(kwargs["json"]["think"])

    @patch("amc.classification.classifier.requests.Session")
    def test_invalid_labels_are_rejected(self, factory):
        session = factory.return_value.__enter__.return_value
        session.post.return_value.json.return_value = {
            "message": {"content": '{"relevance":"relevant","impact":"invented"}'}
        }
        with self.assertRaises(ValueError):
            classify("comment", "qwen3:8b")
