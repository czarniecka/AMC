"""Export Wykop entries and comments that the model labelled ai=yes and work=yes."""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.classification.job_concern import PROMPT_HASH  # noqa: E402
from amc.csv_files import read_rows  # noqa: E402
from amc.wykop import classification, records  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
LABELS = ("ai", "work", "stance", "model", "prompt_hash")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries", type=Path, default=ROOT / "data/wykop/wykop_entries.csv")
    parser.add_argument("--labels", type=Path, default=ROOT / "data/wykop/wykop_classified.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/wykop/wykop_ai_work.csv")
    parser.add_argument("--model", default="qwen3:8b")
    options = parser.parse_args(argv)
    # Only labels from the current instruction and model; older rows stay in the file.
    labels = {
        (row["type"], row["entry_id"]): row
        for row in read_rows(options.labels, classification.COLUMNS)
        if row["prompt_hash"] == PROMPT_HASH
        and row["model"] == options.model
        and row["ai"] == "yes"
        and row["work"] == "yes"
    }
    rows = [
        {**row, **{name: label[name] for name in LABELS}}
        for row in read_rows(options.entries, records.COLUMNS)
        if (label := labels.get((row["type"], row["entry_id"])))
    ]
    rows.sort(key=lambda row: row["created_at"])
    with options.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(*records.COLUMNS, *LABELS))
        writer.writeheader()
        writer.writerows(rows)
    print(f"Saved {len(rows)} texts with ai=yes and work=yes to {options.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
