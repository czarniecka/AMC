"""Write Wykop texts with their ai, work and stance labels to one CSV."""

import argparse
import csv
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv  # noqa: E402

from amc.wykop.classification import LABELED_COLUMNS, labeled  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/wykop/wykop_entries.csv")
    parser.add_argument("--labels", type=Path, default=ROOT / "data/wykop/wykop_classified.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/wykop/wykop_labeled.csv")
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    options = parser.parse_args(argv)
    if options.output.resolve() in {options.input.resolve(), options.labels.resolve()}:
        print("Output must be separate from the input files.", file=sys.stderr)
        return 1
    csv.field_size_limit(2**31 - 1)
    rows, stale = labeled(options.input, options.labels, options.model)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    with options.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=LABELED_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} labeled texts to {options.output}")
    if stale:
        print(f"Skipped {stale} labels whose text changed since classification.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
