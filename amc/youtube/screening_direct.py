"""Run prepared comment groups through concurrent, resumable Responses API calls."""

import json
import os
import random
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from pathlib import Path

import requests as http_requests

from amc.youtube.screening_runner import (
    LEGACY_SCHEME,
    _job,
    _output_text,
    _read_jsonl,
    _write_json,
    validate,
)

BASE_URL = "https://api.openai.com/v1/responses"


class ModelOutputError(ValueError):
    """A model response arrived but could not be used as a complete batch label."""

    def __init__(self, message: str, response_body: dict) -> None:
        super().__init__(message)
        self.response_body = response_body


def _validated_answer(batch: dict, body: dict, label_scheme: str) -> dict:
    """Accept a complete response, or identical valid answers in separate text parts."""
    if body.get("status") != "completed":
        raise ValueError("Model response did not complete")
    parts = [
        item["text"]
        for output in body.get("output", [])
        if output.get("type") == "message"
        for item in output.get("content", [])
        if item.get("type") == "output_text"
    ]
    if not parts:
        _output_text(body)  # Provide the precise status/no-text error.
    candidates = ["".join(parts), *parts] if len(parts) > 1 else parts
    answers = []
    errors = []
    for candidate in candidates:
        try:
            answer = validate(batch, json.loads(candidate), label_scheme)
        except (TypeError, ValueError) as error:
            errors.append(str(error))
        else:
            if answer not in answers:
                answers.append(answer)
    if len(answers) == 1:
        return answers[0]
    if len(answers) > 1:
        raise ValueError("Model response contains conflicting valid answers")
    raise ValueError(f"Invalid labels: {errors[-1] if errors else 'no valid text'}")


def _call(request: dict, job: dict, api_key: str, post, sleep) -> dict:
    batch = json.loads(request["body"]["input"][1]["content"])
    if request["custom_id"] != batch["batch_id"]:
        raise ValueError("Request custom_id differs from its comment batch")
    for attempt in range(4):
        response = post(
            BASE_URL,
            json=request["body"],
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=(10, 300),
        )
        if response.status_code in {429, 500, 502, 503, 504}:
            try:
                error_code = response.json().get("error", {}).get("code")
            except (TypeError, ValueError):
                error_code = None
            if error_code in {"insufficient_quota", "billing_hard_limit_reached"}:
                raise ValueError(f"OpenAI HTTP {response.status_code}: {error_code}")
            if attempt < 3:
                try:
                    retry_after = float(response.headers.get("Retry-After", ""))
                except ValueError:
                    retry_after = 0
                sleep(max(retry_after, min(2**attempt, 30)) + random.random())
                continue
        if response.status_code != 200:
            raise ValueError(f"OpenAI HTTP {response.status_code} for {request['custom_id']}")
        body = response.json()
        try:
            _output_text(body)
            answer = _validated_answer(batch, body, job.get("label_scheme", LEGACY_SCHEME))
        except ValueError as error:
            content_types = [
                content.get("type")
                for output in body.get("output", [])
                for content in output.get("content", [])
            ]
            raise ModelOutputError(
                f"{error}; response status={body.get('status')}; "
                f"content types={content_types}; incomplete={body.get('incomplete_details')}",
                body,
            ) from error
        return {
            "batch_id": batch["batch_id"],
            "model": job["model"],
            "instruction_hash": job["instruction_hash"],
            "source_sha256": job["source_sha256"],
            "answer": answer,
            "usage": body.get("usage"),
        }
    raise RuntimeError("Unreachable retry state")


def run(
    request_dir: Path,
    output_dir: Path,
    *,
    workers: int = 4,
    limit_requests: int | None = None,
    retry_failed: bool = False,
    recover_only: bool = False,
    api_key: str | None = None,
    post=None,
    sleep=time.sleep,
    progress=print,
) -> dict:
    """Save each validated group separately; reruns skip saved groups."""
    if not 1 <= workers <= 32 or limit_requests is not None and limit_requests < 1:
        raise ValueError("workers must be 1-32 and limit_requests must be positive")
    job = _job(request_dir)
    prepared_requests = _read_jsonl(request_dir / "requests.jsonl")
    ids = [item["custom_id"] for item in prepared_requests]
    if len(ids) != len(set(ids)) or ids != job["batch_ids"]:
        raise ValueError("Prepared request IDs differ from job.json")
    if limit_requests is not None:
        prepared_requests = prepared_requests[:limit_requests]
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key and not recover_only:
        raise ValueError("Set OPENAI_API_KEY before calling the Responses API")
    post = post or requests_module_post
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "direct_run.json"
    manifest = {"request_sha256": job["request_sha256"], "request_dir": str(request_dir.resolve())}
    if manifest_path.exists():
        if json.loads(manifest_path.read_text(encoding="utf-8")) != manifest:
            raise ValueError("Output directory belongs to different prepared requests")
    elif any(output_dir.iterdir()):
        raise ValueError("Output directory already contains a different run")
    else:
        _write_json(manifest_path, manifest)
    results_dir = output_dir / "results"
    results_dir.mkdir(exist_ok=True)
    failures_dir = output_dir / "failures"
    failures_dir.mkdir(exist_ok=True)
    raw_responses_dir = output_dir / "raw_responses"
    raw_responses_dir.mkdir(exist_ok=True)
    lock = output_dir / "run.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("This direct run is already active") from None
    os.close(descriptor)
    failures = []
    fatal = False
    try:
        if recover_only:
            for item in prepared_requests:
                batch_id = item["custom_id"]
                raw_path = raw_responses_dir / f"{batch_id}.json"
                result_path = results_dir / f"{batch_id}.json"
                if not raw_path.exists() or result_path.exists():
                    continue
                body = json.loads(raw_path.read_text(encoding="utf-8"))
                batch = json.loads(item["body"]["input"][1]["content"])
                try:
                    answer = _validated_answer(batch, body, job.get("label_scheme", LEGACY_SCHEME))
                except (TypeError, ValueError):
                    continue
                _write_json(
                    result_path,
                    {
                        "batch_id": batch_id,
                        "model": job["model"],
                        "instruction_hash": job["instruction_hash"],
                        "source_sha256": job["source_sha256"],
                        "answer": answer,
                        "usage": body.get("usage"),
                    },
                )
                (failures_dir / f"{batch_id}.json").unlink(missing_ok=True)
                progress(f"Recovered {batch_id}")
        pending = (
            []
            if recover_only
            else [
                item
                for item in prepared_requests
                if not (results_dir / f"{item['custom_id']}.json").exists()
                and (retry_failed or not (failures_dir / f"{item['custom_id']}.json").exists())
            ]
        )
        with ThreadPoolExecutor(max_workers=workers) as executor:
            iterator = iter(pending)
            futures = {}

            def start_next() -> None:
                try:
                    item = next(iterator)
                except StopIteration:
                    return
                future = executor.submit(_call, item, job, key, post, sleep)
                futures[future] = item["custom_id"]

            for _ in range(workers):
                start_next()
            while futures:
                done, _ = wait(futures, return_when=FIRST_COMPLETED)
                for future in done:
                    batch_id = futures.pop(future)
                    try:
                        result = future.result()
                    except ModelOutputError as error:
                        _write_json(raw_responses_dir / f"{batch_id}.json", error.response_body)
                        failure = {
                            "batch_id": batch_id,
                            "kind": "model_output",
                            "error": str(error),
                        }
                        _write_json(failures_dir / f"{batch_id}.json", failure)
                        failures.append(failure)
                        progress(f"Invalid model output for {batch_id}: {error}")
                        if not fatal:
                            start_next()
                        continue
                    except http_requests.ReadTimeout as error:
                        failure = {
                            "batch_id": batch_id,
                            "kind": "uncertain_timeout",
                            "error": str(error),
                        }
                        _write_json(failures_dir / f"{batch_id}.json", failure)
                        failures.append(failure)
                        progress(f"Timed out {batch_id}; completion unknown: {error}")
                        if not fatal:
                            start_next()
                        continue
                    except (
                        KeyError,
                        TypeError,
                        ValueError,
                        http_requests.RequestException,
                    ) as error:
                        fatal = True
                        failures.append({"batch_id": batch_id, "error": str(error)})
                        progress(f"Failed {batch_id}: {error}")
                        continue
                    _write_json(results_dir / f"{batch_id}.json", result)
                    (failures_dir / f"{batch_id}.json").unlink(missing_ok=True)
                    progress(f"Saved {batch_id}")
                    if not fatal:
                        start_next()
        valid = []
        for item in prepared_requests:
            path = results_dir / f"{item['custom_id']}.json"
            if path.exists():
                result = json.loads(path.read_text(encoding="utf-8"))
                batch = json.loads(item["body"]["input"][1]["content"])
                if result["batch_id"] != item["custom_id"]:
                    raise ValueError("Saved result has wrong batch ID")
                validate(batch, result["answer"], job.get("label_scheme", LEGACY_SCHEME))
                valid.append(result)
        temporary = output_dir / "predictions.jsonl.tmp"
        with temporary.open("w", encoding="utf-8") as stream:
            for result in valid:
                stream.write(json.dumps(result, ensure_ascii=False) + "\n")
        os.replace(temporary, output_dir / "predictions.jsonl")
        saved_failures = [
            json.loads(path.read_text(encoding="utf-8"))
            for item in prepared_requests
            if (path := failures_dir / f"{item['custom_id']}.json").exists()
        ]
        report = {
            "expected": len(prepared_requests),
            "valid": len(valid),
            "pending": len(prepared_requests) - len(valid),
            "failed_model_outputs": sum(
                failure.get("kind", "model_output") == "model_output" for failure in saved_failures
            ),
            "uncertain_timeouts": sum(
                failure.get("kind") == "uncertain_timeout" for failure in saved_failures
            ),
            "failures": saved_failures
            + [failure for failure in failures if failure not in saved_failures],
        }
        _write_json(output_dir / "validation_report.json", report)
        return report
    finally:
        lock.unlink(missing_ok=True)


requests_module_post = http_requests.post
