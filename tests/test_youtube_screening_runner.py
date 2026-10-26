"""Offline checks for Batch API request shape, lifecycle, and result validation."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from amc.youtube.screening_runner import fetch, prepare, status, submit, validate


class ScreeningRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "screening"
        self.source.mkdir()
        self.batch = {"batch_id": "b00001", "comments": [{"id": "c1", "text": "AI and work"}]}
        (self.source / "batches.jsonl").write_text(json.dumps(self.batch) + "\n")
        (self.source / "screening_config.json").write_text(
            json.dumps({"batches": 1, "instruction": "Classify", "source_sha256": "abc"})
        )
        self.run_dir = self.root / "run"

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
                self.batch,
                {
                    "batch_id": "b00001",
                    "labels": [{"id": "c1", "h1_related": "no", "job_security_concern": "yes"}],
                },
            )

    def test_prepare_emits_real_batch_api_request(self):
        job = prepare(self.source, self.run_dir)
        request = json.loads((self.run_dir / "requests.jsonl").read_text())
        self.assertEqual(job["batch_ids"], ["b00001"])
        self.assertEqual(request["custom_id"], "b00001")
        self.assertEqual(request["url"], "/v1/responses")
        self.assertEqual(request["body"]["model"], "gpt-6-luna")
        self.assertEqual(json.loads(request["body"]["input"]), self.batch)
        self.assertTrue(request["body"]["text"]["format"]["strict"])
        with self.assertRaisesRegex(ValueError, "already exists"):
            prepare(self.source, self.run_dir)

    def test_submit_status_and_fetch_validate_results(self):
        prepare(self.source, self.run_dir)
        upload = Mock()
        upload.json.return_value = {"id": "file_input"}
        create = Mock()
        create.json.return_value = {"id": "batch_123", "status": "validating"}
        response_status = Mock()
        response_status.json.return_value = {
            "id": "batch_123",
            "status": "completed",
            "output_file_id": "file_output",
            "error_file_id": None,
        }
        answer = {
            "batch_id": "b00001",
            "labels": [{"id": "c1", "h1_related": "yes", "job_security_concern": "no"}],
        }
        output = Mock()
        output.content = (
            json.dumps(
                {
                    "custom_id": "b00001",
                    "response": {
                        "status_code": 200,
                        "body": {
                            "status": "completed",
                            "output": [
                                {
                                    "type": "message",
                                    "content": [
                                        {"type": "output_text", "text": json.dumps(answer)}
                                    ],
                                }
                            ],
                        },
                    },
                    "error": None,
                }
            )
            + "\n"
        ).encode()
        session = Mock()
        session.post.side_effect = [upload, create]
        session.get.side_effect = [response_status, response_status, output]
        job = submit(self.run_dir, api_key="test", session=session)
        self.assertEqual(job["batch_id"], "batch_123")
        self.assertEqual(
            submit(self.run_dir, api_key="test", session=session)["batch_id"], "batch_123"
        )
        self.assertEqual(session.post.call_count, 2)
        self.assertEqual(session.post.call_args_list[0].args[0], "https://api.openai.com/v1/files")
        self.assertEqual(session.post.call_args_list[1].kwargs["json"]["endpoint"], "/v1/responses")
        self.assertEqual(
            status(self.run_dir, api_key="test", session=session)["status"], "completed"
        )
        report = fetch(self.source, self.run_dir, api_key="test", session=session)
        self.assertEqual(report, {"expected": 1, "valid": 1, "failed": 0, "missing": 0})
        self.assertEqual(len((self.run_dir / "predictions.jsonl").read_text().splitlines()), 1)
