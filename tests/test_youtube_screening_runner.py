"""Validate small-model output identity and resume without network calls."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from amc.youtube.screening_runner import run, validate


class ScreeningRunnerTests(unittest.TestCase):
    def test_rejects_incomplete_or_wrong_labels(self):
        batch = {"batch_id": "b00001", "comments": [{"id": "c1"}, {"id": "c2"}]}
        with self.assertRaisesRegex(ValueError, "cover every comment"):
            validate(batch, {"batch_id": "b00001", "labels": []})
        with self.assertRaisesRegex(ValueError, "reordered"):
            validate(
                batch,
                {
                    "batch_id": "b00001",
                    "labels": [
                        {"id": "c2", "h1_related": "yes", "job_security_concern": "no"},
                        {"id": "c1", "h1_related": "yes", "job_security_concern": "no"},
                    ],
                },
            )
        with self.assertRaisesRegex(ValueError, "unrelated"):
            validate(
                {"batch_id": "b00001", "comments": [{"id": "c1"}]},
                {
                    "batch_id": "b00001",
                    "labels": [{"id": "c1", "h1_related": "no", "job_security_concern": "yes"}],
                },
            )

    def test_sends_one_batch_and_resumes_without_repeating(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "screening"
            source.mkdir()
            batch = {"batch_id": "b00001", "comments": [{"id": "c1", "text": "AI and work"}]}
            (source / "batches.jsonl").write_text(json.dumps(batch) + "\n")
            (source / "screening_config.json").write_text(
                json.dumps({"batches": 1, "instruction": "Classify", "source_sha256": "abc"})
            )
            answer = {
                "batch_id": "b00001",
                "labels": [{"id": "c1", "h1_related": "yes", "job_security_concern": "no"}],
            }
            response = Mock()
            response.json.return_value = {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": json.dumps(answer)}],
                    }
                ],
            }
            session = Mock()
            session.post.return_value = response
            output = root / "predictions.jsonl"
            self.assertEqual(run(source, output, api_key="test", session=session), 1)
            self.assertEqual(run(source, output, api_key="test", session=session), 0)
            session.post.assert_called_once()
            request = session.post.call_args.kwargs["json"]
            self.assertEqual(request["model"], "gpt-6-luna")
            self.assertEqual(json.loads(request["input"]), batch)
            self.assertEqual(len(output.read_text().splitlines()), 1)
