"""Prepare comment-only H1 screening batches for a small language model."""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.youtube.screening import prepare  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, default=Path("data/youtube/yt_comments_anonymized.csv")
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="Use comments from the balanced YouTube sample SQLite database instead of --input",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--max-batch-chars", type=int, default=30000)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    try:
        result = prepare(
            args.database or args.input,
            args.output,
            batch_size=args.batch_size,
            max_batch_chars=args.max_batch_chars,
            seed=args.seed,
        )
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(2, f"{error}\n")
    print(f"Prepared {result['comments']} comments in {result['batches']} batches: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
