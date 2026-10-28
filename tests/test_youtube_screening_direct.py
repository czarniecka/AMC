"""Offline checks for concurrent direct screening and safe resume."""

import json as jsonlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

import requests

from amc.youtube.screening_direct import _validated_answer, run
from amc.youtube.screening_runner import prepare


class DirectScreeningTests(unittest.TestCase):
    def test_recovers_valid_second_text_part_without_api_call(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            batch = {"batch_id": "b00001", "comments": [{"id": "c1", "text": "AI at work"}]}
            (source / "batches.jsonl").write_text(jsonlib.dumps(batch) + "\n")
            (source / "screening_config.json").write_text(
                jsonlib.dumps(
                    {
                        "batches": 1,
                        "instruction": "Classify",
                        "source_sha256": "abc",
                        "label_scheme": "annotation_stage1_v1",
                    }
                )
            )
            prepared = root / "prepared"
            prepare(source, prepared)
            output = root / "output"
            output.mkdir()
            (output / "direct_run.json").write_text(
                jsonlib.dumps(
                    {
                        "request_sha256": jsonlib.loads((prepared / "job.json").read_text())[
                            "request_sha256"
                        ],
                        "request_dir": str(prepared.resolve()),
                    }
                )
            )
            (output / "raw_responses").mkdir()
            answer = {
                "batch_id": "b00001",
                "labels": [{"id": "c1", "ai": "yes", "work": "yes", "stance": "none"}],
            }
            body = {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "unusable"},
                            {"type": "output_text", "text": jsonlib.dumps(answer)},
                        ],
                    }
                ],
            }
            (output / "raw_responses/b00001.json").write_text(jsonlib.dumps(body))
            recovered = run(prepared, output, recover_only=True, progress=lambda _: None)
            self.assertEqual((recovered["valid"], recovered["pending"]), (1, 0))
            self.assertEqual(
                jsonlib.loads((output / "results/b00001.json").read_text())["answer"], answer
            )

    def test_rejects_conflicting_valid_text_parts(self):
        batch = {"batch_id": "b00001", "comments": [{"id": "c1"}]}
        first = {
            "batch_id": "b00001",
            "labels": [{"id": "c1", "ai": "yes", "work": "yes", "stance": "threat"}],
        }
        second = {
            "batch_id": "b00001",
            "labels": [{"id": "c1", "ai": "yes", "work": "yes", "stance": "none"}],
        }
        body = {
            "status": "completed",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": jsonlib.dumps(first)},
                        {"type": "output_text", "text": jsonlib.dumps(second)},
                    ],
                }
            ],
        }
        with self.assertRaisesRegex(ValueError, "conflicting valid answers"):
            _validated_answer(batch, body, "annotation_stage1_v1")

    def test_missing_output_is_reported_and_can_be_retried(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            batch = {"batch_id": "b00001", "comments": [{"id": "c1", "text": "AI at work"}]}
            (source / "batches.jsonl").write_text(jsonlib.dumps(batch) + "\n")
            (source / "screening_config.json").write_text(
                jsonlib.dumps(
                    {
                        "batches": 1,
                        "instruction": "Classify",
                        "source_sha256": "abc",
                        "label_scheme": "annotation_stage1_v1",
                    }
                )
            )
            prepared = root / "prepared"
            prepare(source, prepared)
            response = Mock(status_code=200)
            response.json.return_value = {
                "status": "completed",
                "output": [{"type": "message", "content": [{"type": "refusal"}]}],
            }
            output = root / "output"
            sent = []

            def bad_post(*args, **kwargs):
                sent.append("bad")
                return response

            report = run(
                prepared,
                output,
                workers=1,
                api_key="test",
                post=bad_post,
                progress=lambda message: None,
            )
            self.assertEqual((report["valid"], report["pending"]), (0, 1))
            self.assertIn("content types=['refusal']", report["failures"][0]["error"])
            self.assertEqual(report["failed_model_outputs"], 1)
            self.assertTrue((output / "raw_responses/b00001.json").exists())
            self.assertFalse((output / "run.lock").exists())
            run(prepared, output, workers=1, api_key="test", post=bad_post, progress=lambda _: None)
            self.assertEqual(sent, ["bad"])

            answer = {
                "batch_id": "b00001",
                "labels": [{"id": "c1", "ai": "yes", "work": "yes", "stance": "none"}],
            }
            response.json.return_value = {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": jsonlib.dumps(answer)}],
                    }
                ],
            }
            retried = run(
                prepared,
                output,
                workers=1,
                api_key="test",
                post=bad_post,
                retry_failed=True,
                progress=lambda _: None,
            )
            self.assertEqual((retried["valid"], retried["pending"]), (1, 0))
            self.assertEqual(sent, ["bad", "bad"])
            self.assertFalse((output / "failures/b00001.json").exists())

    def test_read_timeout_is_recorded_and_not_repeated_automatically(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            (source / "batches.jsonl").write_text(
                jsonlib.dumps(
                    {"batch_id": "b00001", "comments": [{"id": "c1", "text": "AI at work"}]}
                )
                + "\n"
            )
            (source / "screening_config.json").write_text(
                jsonlib.dumps(
                    {
                        "batches": 1,
                        "instruction": "Classify",
                        "source_sha256": "abc",
                        "label_scheme": "annotation_stage1_v1",
                    }
                )
            )
            prepared = root / "prepared"
            prepare(source, prepared)
            sent = []

            def timeout_post(*args, **kwargs):
                sent.append(1)
                raise requests.ReadTimeout("read timeout")

            output = root / "output"
            first = run(
                prepared, output, api_key="test", post=timeout_post, progress=lambda _: None
            )
            second = run(
                prepared, output, api_key="test", post=timeout_post, progress=lambda _: None
            )
            self.assertEqual(first["uncertain_timeouts"], 1)
            self.assertEqual(second["pending"], 1)
            self.assertEqual(sent, [1])

    def test_sends_one_group_per_request_and_resumes_without_repeating(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source"
            source.mkdir()
            batches = [
                {"batch_id": f"b{i:05d}", "comments": [{"id": f"c{i}", "text": "AI at work"}]}
                for i in (1, 2)
            ]
            (source / "batches.jsonl").write_text(
                "".join(jsonlib.dumps(batch) + "\n" for batch in batches)
            )
            (source / "screening_config.json").write_text(
                jsonlib.dumps(
                    {
                        "batches": 2,
                        "instruction": "Classify",
                        "source_sha256": "abc",
                        "label_scheme": "annotation_stage1_v1",
                    }
                )
            )
            prepared = root / "prepared"
            prepare(source, prepared)
            sent = []

            def post(url, *, json, headers, timeout):
                batch = jsonlib.loads(json["input"][1]["content"])
                sent.append(batch["batch_id"])
                answer = {
                    "batch_id": batch["batch_id"],
                    "labels": [
                        {
                            "id": batch["comments"][0]["id"],
                            "ai": "no",
                            "work": "yes",
                            "stance": "none",
                        }
                    ],
                }
                response = Mock(status_code=200)
                response.json.return_value = {
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": jsonlib.dumps(answer)}],
                        }
                    ],
                    "usage": {"input_tokens": 12, "output_tokens": 9},
                }
                return response

            output = root / "output"
            first = run(prepared, output, workers=1, limit_requests=1, api_key="test", post=post)
            self.assertEqual((first["expected"], first["valid"]), (1, 1))
            second = run(prepared, output, workers=1, api_key="test", post=post)
            self.assertEqual((second["expected"], second["valid"]), (2, 2))
            self.assertEqual(sent, ["b00001", "b00002"])
            self.assertEqual(len((output / "predictions.jsonl").read_text().splitlines()), 2)


if __name__ == "__main__":
    unittest.main()
