"""Classify entries and comments with the H1 labels (`job_concern`), in parallel requests.

`type` and `entry_id` are the key. Rows are appended as answers arrive, because the
collection is too large to rewrite the file after each prediction. Reruns skip rows with the
same key, text hash, model and prompt hash. Invalid answers are not saved and are retried on
the next run.
"""

import hashlib
import random
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from amc.classification.job_concern import PROMPT_HASH, OllamaClient
from amc.csv_files import append_rows, read_rows
from amc.wykop import records

COLUMNS = (
    "type",
    "entry_id",
    "text_hash",
    "ai",
    "work",
    "stance",
    "model",
    "prompt_hash",
    "classified_at",
)
SEED = 20261013
LABELED_COLUMNS = (
    "type",
    "entry_id",
    "parent_id",
    "created_at",
    "url",
    "text",
    "ai",
    "work",
    "stance",
)


# Mirko Anonim posts carry a bot header and footer; since July 2025 the header is an
# AI-written title linking to `#wsparcie-ai`, which the model would read as a post about AI.
BOT_LINE = re.compile(r"mirko\.pro|mirko ?anonim|^\s*[─〰!]+\s*$|^\s*· ", re.I)


def model_text(text: str) -> str:
    """The author's own words: Mirko Anonim header and footer lines removed."""
    if "mirko.pro" not in text:
        return text
    return "\n".join(line for line in text.splitlines() if not BOT_LINE.search(line)).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def completed(output: Path, model: str) -> set[tuple[str, str, str]]:
    return {
        (row["type"], row["entry_id"], row["text_hash"])
        for row in read_rows(output, COLUMNS)
        if row["model"] == model and row["prompt_hash"] == PROMPT_HASH
    }


def run(
    client: OllamaClient,
    source: Path,
    output: Path,
    model: str,
    *,
    workers: int = 2,
    limit: int | None = None,
    seed: int = SEED,
    log: Callable[[str], None] = print,
) -> int:
    """Classify pending texts in a reproducible random order; returns new predictions."""
    if source.resolve() == output.resolve():
        raise ValueError("Classification output must be separate from the source.")
    done = completed(output, model)
    # `text` becomes what the model reads, so `text_hash` changes when the cleaning does.
    rows = [{**row, "text": model_text(row["text"])} for row in read_rows(source, records.COLUMNS)]
    rows = [row for row in rows if row["text"]]
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


def labeled(source: Path, labels: Path, model: str) -> tuple[list[dict[str, str]], int]:
    """Texts joined with their labels from `model` and the current prompt.

    The text is what the model read. Labels of texts that changed since classification are
    left out; their number is returned with the rows.
    """
    current = {
        (row["type"], row["entry_id"]): row
        for row in read_rows(labels, COLUMNS)
        if row["model"] == model and row["prompt_hash"] == PROMPT_HASH
    }
    rows, matched = [], 0
    for row in read_rows(source, records.COLUMNS):
        label = current.get((row["type"], row["entry_id"]))
        if label is None:
            continue
        text = model_text(row["text"])
        if label["text_hash"] != text_hash(text):
            continue
        matched += 1
        values = {**row, "text": text, **label}
        rows.append({column: values[column] for column in LABELED_COLUMNS})
    return rows, len(current) - matched
