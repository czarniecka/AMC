"""Convert frozen screening batches to the stage 1 classifier input and join results back.

The stage 1 classifier (`scripts/wykop/classify_entries.py`) reads a CSV with `type`,
`entry_id` and `text`. Here `entry_id` is the short `item_id` from `manifest.csv`, so the
model and its output never see real YouTube comment ids.
"""

import csv
import json
from pathlib import Path

INPUT_COLUMNS = ("type", "entry_id", "text")
LABELS = ("ai", "work")
MANIFEST_COLUMNS = (
    "item_id",
    "batch_id",
    "video_id",
    "comment_id",
    "published_at",
    "period",
    "text_hash",
)
OUTPUT_COLUMNS = (*MANIFEST_COLUMNS, *LABELS, "model", "prompt_hash")
TYPE = "youtube"


def export_input(screening_dir: Path, output: Path | None = None) -> int:
    """Write one row per comment from batches.jsonl; refuses to overwrite an existing file."""
    output = output or screening_dir / "stage1_input.csv"
    if output.exists():
        raise ValueError(f"{output.name} already exists; remove it or choose another path")
    rows = []
    with (screening_dir / "batches.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                rows.extend(json.loads(line)["comments"])
    ids = [comment["id"] for comment in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("batches.jsonl contains duplicate ids")
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=INPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(
            {"type": TYPE, "entry_id": comment["id"], "text": comment["text"]} for comment in rows
        )
    return len(rows)


def merge_output(
    screening_dir: Path,
    classified: Path | None = None,
    output: Path | None = None,
    *,
    model: str | None = None,
    prompt_hash: str | None = None,
) -> dict[str, int]:
    """Join classifier output with manifest.csv; the output has period and video for analysis."""
    classified = classified or screening_dir / "stage1_output.csv"
    output = output or screening_dir / "stage1_labels.csv"
    with classified.open(encoding="utf-8-sig", newline="") as stream:
        predictions = [row for row in csv.DictReader(stream) if row["type"] == TYPE]
    versions = {(row["model"], row["prompt_hash"]) for row in predictions}
    if model or prompt_hash:
        versions = {
            version
            for version in versions
            if version[0] == (model or version[0]) and version[1] == (prompt_hash or version[1])
        }
    if len(versions) > 1:
        raise ValueError(
            "The output mixes several models or prompts; pass --model and --prompt-hash: "
            + "; ".join(f"{m} {p[:12]}" for m, p in sorted(versions))
        )
    by_id = {
        row["entry_id"]: row
        for row in predictions
        if (row["model"], row["prompt_hash"]) in versions
    }
    with (screening_dir / "manifest.csv").open(encoding="utf-8-sig", newline="") as stream:
        manifest = list(csv.DictReader(stream))
    rows = [{**item, **by_id[item["item_id"]]} for item in manifest if item["item_id"] in by_id]
    with output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return {"manifest": len(manifest), "labeled": len(rows), "missing": len(manifest) - len(rows)}
