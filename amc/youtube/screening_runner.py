"""Send prepared H1 batches to the OpenAI Responses API with resumable validation."""

import hashlib
import json
import os
from pathlib import Path

import requests

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


def run(
    input_dir: Path,
    output_path: Path,
    *,
    model: str = "gpt-6-luna",
    limit_batches: int | None = None,
    api_key: str | None = None,
    session: requests.Session | None = None,
) -> int:
    """Append only validated predictions and resume an unchanged cohort."""
    if limit_batches is not None and limit_batches < 1:
        raise ValueError("limit_batches must be positive")
    if not model.strip():
        raise ValueError("model must be non-empty")
    config = json.loads((input_dir / "screening_config.json").read_text(encoding="utf-8"))
    instruction = config["instruction"]
    instruction_hash = hashlib.sha256(instruction.encode()).hexdigest()
    source_sha256 = config["source_sha256"]
    batches = [
        json.loads(line)
        for line in (input_dir / "batches.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(batches) != config["batches"]:
        raise ValueError("Batch count differs from screening_config.json")
    by_id = {}
    for batch in batches:
        batch_id = batch["batch_id"]
        if batch_id in by_id or not batch["comments"]:
            raise ValueError("Duplicate or empty input batch")
        by_id[batch_id] = batch
    completed = set()
    if output_path.exists():
        with output_path.open(encoding="utf-8") as stream:
            for line in stream:
                row = json.loads(line)
                if (
                    row["batch_id"] not in by_id
                    or row["batch_id"] in completed
                    or row["model"] != model
                    or row["instruction_hash"] != instruction_hash
                    or row["source_sha256"] != source_sha256
                ):
                    raise ValueError("Existing output belongs to a different or invalid run")
                validate(by_id[row["batch_id"]], row["answer"])
                completed.add(row["batch_id"])
    pending = [batch for batch in batches if batch["batch_id"] not in completed]
    if limit_batches is not None:
        pending = pending[:limit_batches]
    if not pending:
        return 0
    key = api_key or os.getenv("OPENAI_API_KEY", "")
    if not key:
        raise ValueError("Set OPENAI_API_KEY before sending screening batches")
    if output_path.resolve() in {
        (input_dir / name).resolve()
        for name in ("batches.jsonl", "manifest.csv", "screening_config.json")
    }:
        raise ValueError("Output must not overwrite frozen screening inputs")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    own_session = session is None
    client = session or requests.Session()
    added = 0
    try:
        with output_path.open("a", encoding="utf-8") as stream:
            for batch in pending:
                response = client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": model,
                        "instructions": instruction,
                        "input": json.dumps(batch, ensure_ascii=False),
                        "text": {
                            "format": {
                                "type": "json_schema",
                                "name": "h1_screening",
                                "strict": True,
                                "schema": SCHEMA,
                            }
                        },
                    },
                    timeout=(10, 300),
                )
                response.raise_for_status()
                answer = validate(batch, json.loads(_output_text(response.json())))
                stream.write(
                    json.dumps(
                        {
                            "batch_id": batch["batch_id"],
                            "model": model,
                            "instruction_hash": instruction_hash,
                            "source_sha256": source_sha256,
                            "answer": answer,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                stream.flush()
                os.fsync(stream.fileno())
                added += 1
                print(f"Validated batch {batch['batch_id']} ({added} new).", flush=True)
    finally:
        if own_session:
            client.close()
    return added
