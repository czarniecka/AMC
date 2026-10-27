"""Send frozen screening batches to a model and keep only validated answers.

Input is a directory made by `prepare_screening.py`. Valid answers are appended to
`results.jsonl` as they arrive, so an interrupted run resumes without repeating batches.
"""

import csv
import hashlib
import json
import os
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

import requests

VALUES = ("yes", "no", "unclear")
FIELDS = ("h1_related", "job_security_concern")
LABEL_COLUMNS = (
    "item_id",
    "batch_id",
    "video_id",
    "comment_id",
    "published_at",
    "period",
    "text_hash",
    *FIELDS,
    "model",
    "prompt_sha256",
)
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
                    **{field: {"type": "string", "enum": list(VALUES)} for field in FIELDS},
                },
                "required": ["id", *FIELDS],
                "additionalProperties": False,
            },
        },
    },
    "required": ["batch_id", "labels"],
    "additionalProperties": False,
}

Ask = Callable[[str, str], object]


def validate_response(batch: dict, payload: object) -> dict[str, dict[str, str]]:
    """Map every input id to its two labels, or raise ValueError for any deviation."""
    if not isinstance(payload, dict) or set(payload) != {"batch_id", "labels"}:
        raise ValueError("Response must be an object with batch_id and labels")
    if payload["batch_id"] != batch["batch_id"]:
        raise ValueError(f"batch_id {payload['batch_id']!r} does not match {batch['batch_id']!r}")
    if not isinstance(payload["labels"], list):
        raise ValueError("labels must be a list")
    expected = [comment["id"] for comment in batch["comments"]]
    found: dict[str, dict[str, str]] = {}
    for entry in payload["labels"]:
        if not isinstance(entry, dict) or set(entry) != {"id", *FIELDS}:
            raise ValueError("Each label needs exactly id, h1_related and job_security_concern")
        if entry["id"] in found:
            raise ValueError(f"Duplicate id {entry['id']!r}")
        if any(entry[field] not in VALUES for field in FIELDS):
            raise ValueError(f"Invalid label value for id {entry['id']!r}")
        if entry["h1_related"] == "no" and entry["job_security_concern"] != "no":
            raise ValueError(f"h1_related=no requires job_security_concern=no ({entry['id']!r})")
        found[entry["id"]] = {field: entry[field] for field in FIELDS}
    if set(found) != set(expected):
        missing = len(set(expected) - set(found))
        unknown = len(set(found) - set(expected))
        raise ValueError(f"Ids differ from the input: {missing} missing, {unknown} unknown")
    return found


class OllamaChat:
    """One non-conversational request per call, constrained by the response schema."""

    def __init__(self, base_url: str, model: str, *, num_ctx: int = 16384) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx

    def __call__(self, instruction: str, user_message: str) -> object:
        with requests.Session() as session:
            session.trust_env = False
            response = session.post(
                self.base_url + "/api/chat",
                json={
                    "model": self.model,
                    "think": False,
                    "stream": False,
                    "keep_alive": "30m",
                    "format": SCHEMA,
                    "options": {"temperature": 0, "num_ctx": self.num_ctx, "num_predict": 8192},
                    "messages": [
                        {"role": "system", "content": instruction},
                        {"role": "user", "content": user_message},
                    ],
                },
                timeout=(5, 1800),
            )
            response.raise_for_status()
            payload = response.json()
        if payload.get("done_reason") == "length":
            raise ValueError("The model response reached the output limit")
        return json.loads(payload["message"]["content"])


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _append_jsonl(path: Path, record: dict) -> None:
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


def _halves(batch: dict) -> tuple[dict, dict]:
    comments = batch["comments"]
    middle = len(comments) // 2
    return (
        {"batch_id": batch["batch_id"], "comments": comments[:middle]},
        {"batch_id": batch["batch_id"], "comments": comments[middle:]},
    )


def label_batch(
    batch: dict, instruction: str, ask: Ask, *, max_retries: int, min_split: int
) -> tuple[dict[str, dict[str, str]], int]:
    """Validated labels for one batch; a failing batch is split in halves down to min_split."""
    message = json.dumps(batch, ensure_ascii=False)
    last_error = "no attempt"
    for attempt in range(1, max_retries + 1):
        try:
            return validate_response(batch, ask(instruction, message)), attempt
        except (ValueError, KeyError) as error:
            # Connection and HTTP errors are not caught: the run stops instead of failing
            # every remaining batch, and saved results are kept for the next run.
            last_error = f"{type(error).__name__}: {error}"
    if len(batch["comments"]) <= min_split:
        raise ValueError(
            f"Batch {batch['batch_id']} failed after {max_retries} tries: {last_error}"
        )
    labels: dict[str, dict[str, str]] = {}
    attempts = max_retries
    for half in _halves(batch):
        part, used = label_batch(
            half, instruction, ask, max_retries=max_retries, min_split=min_split
        )
        labels.update(part)
        attempts += used
    return labels, attempts


def run(
    screening_dir: Path,
    ask: Ask,
    model: str,
    *,
    max_retries: int = 3,
    min_split: int = 10,
    limit: int | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, int]:
    """Label pending batches; returns counts of labeled, failed and still pending batches."""
    config = json.loads((screening_dir / "screening_config.json").read_text(encoding="utf-8"))
    instruction = config["instruction"]
    prompt_hash = hashlib.sha256(instruction.encode("utf-8")).hexdigest()
    batches = _read_jsonl(screening_dir / "batches.jsonl")
    results_path = screening_dir / "results.jsonl"
    done = _read_jsonl(results_path)
    for record in done:
        if (record["model"], record["prompt_sha256"]) != (model, prompt_hash):
            raise ValueError("results.jsonl was made with another model or instruction")
    finished = {record["batch_id"] for record in done}
    pending = [batch for batch in batches if batch["batch_id"] not in finished]
    labeled = failed = 0
    for batch in pending[:limit]:
        try:
            labels, attempts = label_batch(
                batch, instruction, ask, max_retries=max_retries, min_split=min_split
            )
        except ValueError as error:
            failed += 1
            _append_jsonl(
                screening_dir / "failures.jsonl",
                {"batch_id": batch["batch_id"], "error": str(error)},
            )
            log(f"FAILED {batch['batch_id']}: {error}")
            continue
        _append_jsonl(
            results_path,
            {
                "batch_id": batch["batch_id"],
                "labels": [{"id": key, **value} for key, value in labels.items()],
                "model": model,
                "prompt_sha256": prompt_hash,
                "attempts": attempts,
                "labeled_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        labeled += 1
        log(f"ok {batch['batch_id']} ({len(batch['comments'])} comments, {attempts} calls)")
    remaining = len(pending) - labeled - failed
    return {"labeled": labeled, "failed": failed, "pending": remaining}


def merge(screening_dir: Path) -> dict[str, int]:
    """Join results with manifest.csv into labels.csv; report items that still lack labels."""
    with (screening_dir / "manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
        manifest = list(csv.DictReader(stream))
    by_id: dict[str, dict[str, str]] = {}
    for record in _read_jsonl(screening_dir / "results.jsonl"):
        for entry in record["labels"]:
            by_id[entry["id"]] = {
                **{field: entry[field] for field in FIELDS},
                "model": record["model"],
                "prompt_sha256": record["prompt_sha256"],
            }
    rows = [{**item, **by_id[item["item_id"]]} for item in manifest if item["item_id"] in by_id]
    with (screening_dir / "labels.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=LABEL_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return {"manifest": len(manifest), "labeled": len(rows), "missing": len(manifest) - len(rows)}


def default_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
