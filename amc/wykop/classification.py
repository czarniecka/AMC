"""Classify entries and comments in parallel requests, for stage 1 or stage 2 labels.

Stage 1 (`job_concern`: ai, work) writes `wykop_stage1.csv`; the older
`wykop_classified.csv` also has a `stance` column and is kept only as history. Stage 2
(`job_concern_details`) writes `STAGE2_COLUMNS` to `wykop_stage2.csv`. `type` and
`entry_id` are the key. Rows are appended as answers arrive, because the collection is too
large to rewrite the file after each prediction. Reruns skip rows with the same key, text
hash, model and prompt hash. Invalid answers are not saved and are retried on the next run.
"""

import csv
import hashlib
import random
import re
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from amc.classification import job_concern_details
from amc.classification.job_concern import PROMPT_HASH, OllamaClient
from amc.csv_files import append_rows, read_rows
from amc.wykop import records

COLUMNS = (
    "type",
    "entry_id",
    "text_hash",
    "ai",
    "work",
    "model",
    "prompt_hash",
    "classified_at",
)
STAGE2_COLUMNS = (
    "type",
    "entry_id",
    "text_hash",
    *job_concern_details.LABELS,
    "model",
    "prompt_hash",
    "classified_at",
)
SOURCE_COLUMNS = {"type", "entry_id", "text"}
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


def completed(
    output: Path, model: str, columns: tuple[str, ...] = COLUMNS, prompt_hash: str = PROMPT_HASH
) -> set[tuple[str, str, str]]:
    return {
        (row["type"], row["entry_id"], row["text_hash"])
        for row in read_rows(output, columns)
        if row["model"] == model and row["prompt_hash"] == prompt_hash
    }


def source_rows(path: Path) -> list[dict[str, str]]:
    """Texts to classify: any CSV with type, entry_id and text, such as wykop_entries.csv or
    an export like wykop_ai_work.csv."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not SOURCE_COLUMNS <= set(reader.fieldnames or ()):
            raise ValueError(f"{path.name} needs the columns {', '.join(sorted(SOURCE_COLUMNS))}")
        return list(reader)


def run(
    client: OllamaClient,
    source: Path,
    output: Path,
    model: str,
    *,
    columns: tuple[str, ...] = COLUMNS,
    prompt_hash: str = PROMPT_HASH,
    workers: int = 2,
    limit: int | None = None,
    seed: int = SEED,
    log: Callable[[str], None] = print,
) -> int:
    """Classify pending texts in a reproducible random order; returns new predictions."""
    if source.resolve() == output.resolve():
        raise ValueError("Classification output must be separate from the source.")
    done = completed(output, model, columns, prompt_hash)
    # `text` becomes what the model reads, so `text_hash` changes when the cleaning does.
    rows = [{**row, "text": model_text(row["text"])} for row in source_rows(source)]
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
            "prompt_hash": prompt_hash,
            "classified_at": datetime.now(timezone.utc).isoformat(),
        }

    pool = ThreadPoolExecutor(workers)
    with append_rows(output, columns) as (stream, writer):
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
