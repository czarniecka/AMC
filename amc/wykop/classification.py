"""Classify entries and comments like YouTube comments, with parallel CLARIN-PL requests.

Output columns match yt_comments_classified.csv, with `type` and `entry_id` as the key.
Rows are appended as answers arrive, because the collection is too large to rewrite the file
after each prediction. Reruns skip rows with the same key, text hash, model and prompt hash.
Invalid answers are not saved and are retried on the next run.
"""

import hashlib
import random
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from amc.classification.batch_classifier import PROMPT_HASH
from amc.classification.clarin import ClarinClient
from amc.csv_files import append_rows, read_rows
from amc.wykop import records

COLUMNS = (
    "type",
    "entry_id",
    "text_hash",
    "relevance",
    "impact",
    "model",
    "prompt_hash",
    "classified_at",
)
SEED = 20261013


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def completed(output: Path, model: str) -> set[tuple[str, str, str]]:
    return {
        (row["type"], row["entry_id"], row["text_hash"])
        for row in read_rows(output, COLUMNS)
        if row["model"] == model and row["prompt_hash"] == PROMPT_HASH
    }


def run(
    client: ClarinClient,
    source: Path,
    output: Path,
    model: str,
    *,
    workers: int = 8,
    limit: int | None = None,
    seed: int = SEED,
    log: Callable[[str], None] = print,
) -> int:
    """Classify pending texts in a reproducible random order; returns new predictions."""
    if source.resolve() == output.resolve():
        raise ValueError("Classification output must be separate from the source.")
    done = completed(output, model)
    rows = [row for row in read_rows(source, records.COLUMNS) if row["text"].strip()]
    random.Random(seed).shuffle(rows)
    todo = [
        row for row in rows if (row["type"], row["entry_id"], text_hash(row["text"])) not in done
    ][:limit]
    log(f"Model {model}: {len(todo)} texts to classify, {workers} parallel requests.")
    added = invalid = 0
    started = time.time()

    def task(row: dict[str, str]) -> dict[str, str] | None:
        try:
            labels = client.classify(row["text"], model)
        except ValueError:
            return None
        return {
            "type": row["type"],
            "entry_id": row["entry_id"],
            "text_hash": text_hash(row["text"]),
            **labels,
            "model": model,
            "prompt_hash": PROMPT_HASH,
            "classified_at": datetime.now(timezone.utc).isoformat(),
        }

    pool = ThreadPoolExecutor(workers)
    with append_rows(output, COLUMNS) as (stream, writer):
        try:
            jobs = [pool.submit(task, row) for row in todo]
            for n, job in enumerate(as_completed(jobs), 1):
                result = job.result()
                if result is None:
                    invalid += 1
                else:
                    writer.writerow(result)
                    stream.flush()
                    added += 1
                if n % 100 == 0 or (limit and limit <= 20):
                    hours = (time.time() - started) / n * (len(todo) - n) / 3600
                    log(f"{n}/{len(todo)} classified, {invalid} invalid, ~{hours:.1f} h left")
        finally:
            pool.shutdown(wait=False, cancel_futures=True)
    log(f"Saved {added} predictions; {invalid} invalid answers will be retried next run.")
    return added
