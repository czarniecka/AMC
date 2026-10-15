"""Safe updates of existing blind annotation sheets, without model access."""

import csv
import hashlib
import os
import shutil
import tempfile
from pathlib import Path

from amc.youtube.validation import KEY, SHEET, fingerprint, labels, read, unique


def disagreements(
    rows: list[dict], key_path: Path, predictions: Path, cohort: tuple[str, str]
) -> list[int]:
    """Match exact source identity/text and one model/prompt cohort; never guess missing matches."""
    keys = unique(read(key_path, KEY), "sample_id")
    found = {}
    for prediction in read(
        predictions,
        ("video_id", "comment_id", "text_hash", "model", "prompt_hash", "relevance", "impact"),
    ):
        if (prediction["model"], prediction["prompt_hash"]) != cohort:
            continue
        identity = (prediction["video_id"], prediction["comment_id"], prediction["text_hash"])
        if identity in found:
            raise ValueError("Duplicate model predictions")
        found[identity] = prediction
    result = []
    for index, row in enumerate(rows):
        if not row["relevance"] or not row["impact"]:
            continue
        key = keys[row["sample_id"]]
        if fingerprint(row["text_clean"]) != key["text_hash"]:
            raise ValueError("Comment text differs from frozen sample")
        prediction = found.get((key["video_id"], key["comment_id"], key["text_hash"]))
        if prediction is None:
            raise ValueError("Missing predictions for this sheet and selected cohort")
        if any(row[field] != prediction[field] for field in ("relevance", "impact")):
            result.append(index)
    return result


def load_sheet(path: Path) -> tuple[list[dict], str]:
    """Keep a content fingerprint to detect changes by another browser session."""
    content = path.read_bytes()
    rows = read(path, SHEET)
    unique(rows, "sample_id")
    if not rows:
        raise ValueError("The sheet is empty.")
    if set(rows[0]) != set(SHEET):
        raise ValueError("This tool accepts blind annotation sheets only.")
    for row in rows:
        if row["relevance"] or row["impact"]:
            labels(row)
    if content != path.read_bytes():
        raise ValueError("The sheet changed while loading. Reload it.")
    return rows, hashlib.sha256(content).hexdigest()


def save_label(
    path: Path, sample_id: str, relevance: str, impact: str, note: str, expected: str
) -> None:
    """Back up once and atomically update labels only; reject concurrent modifications."""
    labels({"relevance": relevance, "impact": impact})
    lock = path.with_suffix(path.suffix + ".edit.lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise ValueError("Another save is in progress. Try again shortly.") from None
    os.close(descriptor)
    temporary = None
    try:
        rows, actual = load_sheet(path)
        if expected != actual:
            raise ValueError("Someone changed this sheet. Reload before saving.")
        by_id = unique(rows, "sample_id")
        if sample_id not in by_id:
            raise ValueError("Unknown sample ID.")
        row = by_id[sample_id]
        row.update(relevance=relevance, impact=impact, note=note)
        backup = path.parent / "backups" / (path.name + ".before-tool.csv")
        backup.parent.mkdir(exist_ok=True)
        if not backup.exists():
            with backup.open("xb") as target, path.open("rb") as source:
                shutil.copyfileobj(source, target)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8-sig", newline="", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            writer = csv.DictWriter(stream, fieldnames=SHEET)
            writer.writeheader()
            writer.writerows(rows)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)
