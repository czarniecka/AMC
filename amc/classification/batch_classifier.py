"""Resumable CSV classification through Ollama, without modifying source comments."""

import argparse
import csv
import hashlib
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests
from dotenv import load_dotenv

from amc.classification.classifier import IMPACT, INSTRUCTION, RELEVANCE, classify
from amc.youtube.exporter import write_csv

COLUMNS = (
    "video_id",
    "comment_id",
    "text_hash",
    "relevance",
    "impact",
    "model",
    "prompt_hash",
    "classified_at",
)
PROMPT_HASH = hashlib.sha256(INSTRUCTION.encode()).hexdigest()


@dataclass
class Classification:
    video_id: str
    comment_id: str
    text_hash: str
    relevance: str
    impact: str
    model: str
    prompt_hash: str
    classified_at: str


def read_rows(path: Path, required: tuple[str, ...]) -> list[dict[str, str]]:
    """Reject incompatible CSV headers rather than overwriting unknown data."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(required).issubset(reader.fieldnames or ()):
            raise ValueError("CSV headers do not match the expected schema.")
        return list(reader)


def run(
    input_path: Path,
    output_path: Path,
    model: str,
    limit: int | None = None,
    seed: int | None = None,
) -> int:
    """Persist every prediction atomically; skip unchanged completed classifications."""
    if input_path.resolve() == output_path.resolve():
        raise ValueError("Classification output must be separate from source comments.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lock = output_path.with_suffix(output_path.suffix + ".lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("Classification already running. Check the output lock file.") from None
    os.close(descriptor)
    try:
        rows = read_rows(input_path, ("video_id", "comment_id", "text_clean"))
        if seed is not None:
            random.Random(seed).shuffle(rows)
        saved = (
            [Classification(**row) for row in read_rows(output_path, COLUMNS)]
            if output_path.exists()
            else []
        )
        if any(
            row.relevance not in RELEVANCE
            or row.impact not in IMPACT
            or (row.relevance == "unrelated" and row.impact != "unclear")
            for row in saved
        ):
            raise ValueError("Existing output contains invalid labels; it was not changed.")
        completed = {
            (row.video_id, row.comment_id, row.text_hash, row.model, row.prompt_hash)
            for row in saved
        }
        if not output_path.exists():
            write_csv(output_path, COLUMNS, saved)
        added = 0
        for row in rows:
            text = row["text_clean"]
            if text.startswith("'") and text[1:].lstrip().startswith(("=", "+", "-", "@")):
                text = text[1:]
            text_hash = hashlib.sha256(text.encode()).hexdigest()
            key = (row["video_id"], row["comment_id"], text_hash, model, PROMPT_HASH)
            if key in completed:
                continue
            if limit is not None and added >= limit:
                break
            labels = classify(text, model)
            saved.append(
                Classification(
                    row["video_id"],
                    row["comment_id"],
                    text_hash,
                    labels["relevance"],
                    labels["impact"],
                    model,
                    PROMPT_HASH,
                    datetime.now(timezone.utc).isoformat(),
                )
            )
            write_csv(output_path, COLUMNS, saved)
            completed.add(key)
            added += 1
            print(f"Classified {added} new comments; {len(saved)} saved predictions.", flush=True)
        return added
    finally:
        lock.unlink(missing_ok=True)


def main() -> int:
    """Load local configuration and report safe failures without comment text."""
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(description="Classify comments using local Ollama")
    parser.add_argument(
        "--input", type=Path, default=Path("data/youtube/yt_comments_anonymized.csv")
    )
    parser.add_argument(
        "--output", type=Path, default=Path("data/youtube/yt_comments_classified.csv")
    )
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    parser.add_argument("--limit", type=int, help="Maximum new predictions in this run")
    parser.add_argument(
        "--seed", type=int, help="Reproducibly shuffle source rows before processing"
    )
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be positive")
    try:
        start = time.perf_counter()
        added = run(args.input, args.output, args.model, args.limit, args.seed)
    except KeyboardInterrupt:
        print("Interrupted. Saved predictions are retained; rerun to resume.")
        return 130
    except (OSError, ValueError, KeyError, TypeError, csv.Error, requests.RequestException):
        print(
            "Classification stopped. Check Ollama, installed model and CSV files. "
            "Saved predictions are retained; rerun to resume."
        )
        return 1
    elapsed = time.perf_counter() - start
    print(f"Completed: {added} new predictions in {elapsed:.1f} seconds.")
    if added:
        print(f"Mean wall time: {elapsed / added:.2f} seconds per comment.")
    return 0
