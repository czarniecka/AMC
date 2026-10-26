"""Label prepared H1 comment batches with an OpenAI small model."""

import argparse
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.youtube.screening_runner import run  # noqa: E402


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--limit-batches", type=int)
    args = parser.parse_args()
    try:
        added = run(
            args.input_dir,
            args.output,
            model=args.model,
            limit_batches=args.limit_batches,
        )
    except (OSError, ValueError, KeyError, requests.RequestException) as error:
        print(f"Screening stopped: {error}", file=sys.stderr)
        return 1
    print(f"Saved {added} new batches to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
