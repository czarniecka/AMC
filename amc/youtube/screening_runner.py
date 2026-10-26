"""Prepare, submit, and validate H1 screening through the OpenAI Batch API."""

import hashlib
import json
import os
import tempfile
from pathlib import Path

import requests

BASE_URL = "https://api.openai.com/v1"
REQUESTS_FILE = "requests.jsonl"
JOB_FILE = "job.json"
RESULTS_FILE = "results.jsonl"
ERRORS_FILE = "errors.jsonl"
PREDICTIONS_FILE = "predictions.jsonl"

SCHEMA = {
    "type": "object",
    "properties": {
        "batch_id": {"type": "string"},
        "labels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "h1_related": {"type": "string", "enum": ["yes", "no", "unclear"]},
                    "job_security_concern": {"type": "string", "enum": ["yes", "no", "unclear"]},
                },
                "required": ["id", "h1_related", "job_security_concern"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["batch_id", "labels"],
    "additionalProperties": False,
}


def _write_json(path: Path, value: dict) -> None:
    """Replace state atomically."""
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _load_inputs(input_dir: Path) -> tuple[dict, list[dict]]:
    config = json.loads((input_dir / "screening_config.json").read_text(encoding="utf-8"))
    batches = _read_jsonl(input_dir / "batches.jsonl")
    if len(batches) != config["batches"] or not batches:
        raise ValueError("Prepared batch count differs from screening_config.json")
    seen = set()
    for batch in batches:
        if batch["batch_id"] in seen or not batch["comments"]:
            raise ValueError("Duplicate or empty prepared batch")
        seen.add(batch["batch_id"])
        ids = [item["id"] for item in batch["comments"]]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate comment ID within a prepared batch")
    return config, batches


def validate(batch: dict, answer: object) -> dict:
    """Reject missing, duplicate, invented, or logically inconsistent labels."""
    if not isinstance(answer, dict) or set(answer) != {"batch_id", "labels"}:
        raise ValueError("Model response must contain batch_id and labels")
    if answer["batch_id"] != batch["batch_id"] or not isinstance(answer["labels"], list):
        raise ValueError("Model response has a wrong batch ID or labels type")
    expected = [comment["id"] for comment in batch["comments"]]
    labels = answer["labels"]
    if len(labels) != len(expected):
        raise ValueError("Model response does not cover every comment")
    for item, item_id in zip(labels, expected, strict=True):
        if not isinstance(item, dict) or set(item) != {
            "id",
            "h1_related",
            "job_security_concern",
        }:
            raise ValueError("Model response has an invalid label object")
        if item["id"] != item_id or any(
            item[field] not in {"yes", "no", "unclear"}
            for field in ("h1_related", "job_security_concern")
        ):
            raise ValueError("Model response has a missing, reordered, or invalid label")
        if item["h1_related"] == "no" and item["job_security_concern"] != "no":
            raise ValueError("An unrelated comment cannot have a job-security concern label")
    return answer


def _output_text(response: dict) -> str:
    if response.get("status") != "completed":
        raise ValueError("Model response did not complete")
    parts = [
        item["text"]
        for output in response.get("output", [])
        if output.get("type") == "message"
        for item in output.get("content", [])
        if item.get("type") == "output_text"
    ]
    if len(parts) != 1:
        raise ValueError("Model response must contain exactly one text output")
    return parts[0]


def prepare(
    input_dir: Path,
    run_dir: Path,
    *,
    model: str = "gpt-6-luna",
    limit_batches: int | None = None,
    skip_batches: int = 0,
) -> dict:
    """Create an OpenAI Batch API request file from frozen project batches."""
    if run_dir.exists():
        raise ValueError("Run directory already exists; choose a new path")
    if not model.strip() or (limit_batches is not None and limit_batches < 1) or skip_batches < 0:
        raise ValueError("Provide a model, a nonnegative skip, and a positive limit_batches")
    config, batches = _load_inputs(input_dir)
    selected = batches[skip_batches:]
    if limit_batches is not None:
        selected = selected[:limit_batches]
    if not selected:
        raise ValueError("No batches selected")
    run_dir.mkdir(parents=True)
    requests_path = run_dir / REQUESTS_FILE
    instruction_hash = hashlib.sha256(config["instruction"].encode()).hexdigest()
    cache_key = f"amc:h1:{instruction_hash[:16]}"
    with requests_path.open("w", encoding="utf-8") as stream:
        for batch in selected:
            request = {
                "custom_id": batch["batch_id"],
                "method": "POST",
                "url": "/v1/responses",
                "body": {
                    "model": model,
                    "reasoning": {"effort": "none"},
                    "prompt_cache_key": cache_key,
                    "prompt_cache_options": {"mode": "explicit", "ttl": "30m"},
                    "input": [
                        {
                            "role": "developer",
                            "content": [
                                {
                                    "type": "input_text",
                                    "text": config["instruction"],
                                    "prompt_cache_breakpoint": {"mode": "explicit"},
                                }
                            ],
                        },
                        {"role": "user", "content": json.dumps(batch, ensure_ascii=False)},
                    ],
                    "text": {
                        "format": {
                            "type": "json_schema",
                            "name": "h1_screening",
                            "strict": True,
                            "schema": SCHEMA,
                        }
                    },
                },
            }
            stream.write(json.dumps(request, ensure_ascii=False) + "\n")
    job = {
        "model": model,
        "source_sha256": config["source_sha256"],
        "batches_sha256": hashlib.sha256((input_dir / "batches.jsonl").read_bytes()).hexdigest(),
        "instruction_hash": instruction_hash,
        "prompt_cache_key": cache_key,
        "request_sha256": hashlib.sha256(requests_path.read_bytes()).hexdigest(),
        "batch_ids": [batch["batch_id"] for batch in selected],
        "input_file_id": None,
        "batch_id": None,
        "status": "prepared",
        "output_file_id": None,
        "error_file_id": None,
    }
    _write_json(run_dir / JOB_FILE, job)
    return job


def _job(run_dir: Path) -> dict:
    job = json.loads((run_dir / JOB_FILE).read_text(encoding="utf-8"))
    actual = hashlib.sha256((run_dir / REQUESTS_FILE).read_bytes()).hexdigest()
    if actual != job["request_sha256"]:
        raise ValueError("Batch request file changed after preparation")
    return job


def _client(api_key: str | None, session: requests.Session | None) -> tuple[requests.Session, bool]:
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("Set OPENAI_API_KEY before using the OpenAI Batch API")
    client = session or requests.Session()
    client.headers.update({"Authorization": f"Bearer {key}"})
    return client, session is None


def submit(
    run_dir: Path, *, api_key: str | None = None, session: requests.Session | None = None
) -> dict:
    """Upload the request file once, then create one asynchronous Batch job."""
    job = _job(run_dir)
    if job["batch_id"]:
        return job
    client, owned = _client(api_key, session)
    try:
        if not job["input_file_id"]:
            with (run_dir / REQUESTS_FILE).open("rb") as stream:
                response = client.post(
                    f"{BASE_URL}/files",
                    data={"purpose": "batch"},
                    files={"file": (REQUESTS_FILE, stream, "application/jsonl")},
                    timeout=(10, 300),
                )
            response.raise_for_status()
            job["input_file_id"] = response.json()["id"]
            _write_json(run_dir / JOB_FILE, job)
        response = client.post(
            f"{BASE_URL}/batches",
            json={
                "input_file_id": job["input_file_id"],
                "endpoint": "/v1/responses",
                "completion_window": "24h",
            },
            timeout=(10, 60),
        )
        response.raise_for_status()
        batch = response.json()
        job["batch_id"] = batch["id"]
        job["status"] = batch["status"]
        _write_json(run_dir / JOB_FILE, job)
        return job
    finally:
        if owned:
            client.close()


def status(
    run_dir: Path, *, api_key: str | None = None, session: requests.Session | None = None
) -> dict:
    """Refresh Batch status without submitting another job."""
    job = _job(run_dir)
    if not job["batch_id"]:
        raise ValueError("Submit this run before checking status")
    client, owned = _client(api_key, session)
    try:
        response = client.get(f"{BASE_URL}/batches/{job['batch_id']}", timeout=(10, 60))
        response.raise_for_status()
        batch = response.json()
        if batch["id"] != job["batch_id"]:
            raise ValueError("OpenAI returned a different Batch ID")
        job["status"] = batch["status"]
        job["output_file_id"] = batch.get("output_file_id")
        job["error_file_id"] = batch.get("error_file_id")
        _write_json(run_dir / JOB_FILE, job)
        return job
    finally:
        if owned:
            client.close()


def _download(client: requests.Session, file_id: str, target: Path) -> None:
    if target.exists():
        return
    response = client.get(f"{BASE_URL}/files/{file_id}/content", timeout=(10, 300))
    response.raise_for_status()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(response.content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def fetch(
    input_dir: Path,
    run_dir: Path,
    *,
    api_key: str | None = None,
    session: requests.Session | None = None,
) -> dict[str, int]:
    """Download output and write only fully validated predictions."""
    config, batches = _load_inputs(input_dir)
    by_id = {batch["batch_id"]: batch for batch in batches}
    job = _job(run_dir)
    if (
        job["source_sha256"] != config["source_sha256"]
        or job["batches_sha256"]
        != hashlib.sha256((input_dir / "batches.jsonl").read_bytes()).hexdigest()
        or job["instruction_hash"] != hashlib.sha256(config["instruction"].encode()).hexdigest()
    ):
        raise ValueError("This run belongs to a different prepared input")
    if (run_dir / PREDICTIONS_FILE).exists():
        raise ValueError("Predictions already exist; do not overwrite reviewed output")
    job = status(run_dir, api_key=api_key, session=session)
    if job["status"] not in {"completed", "failed", "expired", "cancelled"}:
        raise ValueError(f"Batch is not finished: {job['status']}")
    client, owned = _client(api_key, session)
    try:
        if job["output_file_id"]:
            _download(client, job["output_file_id"], run_dir / RESULTS_FILE)
        if job["error_file_id"]:
            _download(client, job["error_file_id"], run_dir / ERRORS_FILE)
    finally:
        if owned:
            client.close()
    rows = _read_jsonl(run_dir / RESULTS_FILE) if (run_dir / RESULTS_FILE).exists() else []
    expected = set(job["batch_ids"])
    predictions = {}
    failures = []
    seen = set()
    usage_totals = {
        "requests_with_usage": 0,
        "requests_with_cache_hits": 0,
        "input_tokens": 0,
        "cached_input_tokens": 0,
        "cache_write_input_tokens": 0,
        "output_tokens": 0,
        "reasoning_output_tokens": 0,
    }
    for row in rows:
        custom_id = row.get("custom_id")
        if custom_id not in expected or custom_id in seen:
            raise ValueError("Unexpected or duplicate custom_id in Batch results")
        seen.add(custom_id)
        response = row.get("response")
        if row.get("error") or not response or response.get("status_code") != 200:
            failures.append(custom_id)
            continue
        try:
            answer = validate(by_id[custom_id], json.loads(_output_text(response["body"])))
        except (KeyError, TypeError, ValueError):
            failures.append(custom_id)
            continue
        predictions[custom_id] = {
            "batch_id": custom_id,
            "model": job["model"],
            "instruction_hash": job["instruction_hash"],
            "source_sha256": job["source_sha256"],
            "answer": answer,
            "usage": response["body"].get("usage"),
        }
        usage = response["body"].get("usage")
        if isinstance(usage, dict):
            input_details = usage.get("input_tokens_details") or {}
            output_details = usage.get("output_tokens_details") or {}
            usage_totals["requests_with_usage"] += 1
            usage_totals["input_tokens"] += int(usage.get("input_tokens") or 0)
            cached = int(input_details.get("cached_tokens") or 0)
            usage_totals["cached_input_tokens"] += cached
            usage_totals["requests_with_cache_hits"] += int(cached > 0)
            usage_totals["cache_write_input_tokens"] += int(
                input_details.get("cache_write_tokens") or 0
            )
            usage_totals["output_tokens"] += int(usage.get("output_tokens") or 0)
            usage_totals["reasoning_output_tokens"] += int(
                output_details.get("reasoning_tokens") or 0
            )
    if (run_dir / ERRORS_FILE).exists():
        for row in _read_jsonl(run_dir / ERRORS_FILE):
            custom_id = row.get("custom_id")
            if custom_id not in expected or custom_id in seen:
                raise ValueError("Unexpected or duplicate custom_id in Batch errors")
            seen.add(custom_id)
            failures.append(custom_id)
    missing = sorted(expected - seen)
    with (run_dir / PREDICTIONS_FILE).open("x", encoding="utf-8") as stream:
        for custom_id in job["batch_ids"]:
            if custom_id in predictions:
                stream.write(json.dumps(predictions[custom_id], ensure_ascii=False) + "\n")
    report = {
        "expected": len(expected),
        "valid": len(predictions),
        "failed": len(failures),
        "missing": len(missing),
        **usage_totals,
    }
    _write_json(run_dir / "validation_report.json", report)
    return report
