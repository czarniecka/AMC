"""Manage asynchronous H1 screening jobs with the OpenAI Batch API."""

import argparse
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.youtube.screening_runner import fetch, prepare, status, submit  # noqa: E402


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "submit", "status", "fetch"))
    parser.add_argument("--input-dir", type=Path)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--model", default="gpt-6-luna")
    parser.add_argument("--limit-batches", type=int)
    args = parser.parse_args()
    if args.command in {"prepare", "fetch"} and not args.input_dir:
        parser.error("--input-dir is required for prepare and fetch")
    try:
        if args.command == "prepare":
            result = prepare(
                args.input_dir,
                args.run_dir,
                model=args.model,
                limit_batches=args.limit_batches,
            )
            print(f"Prepared {len(result['batch_ids'])} API requests in {args.run_dir}")
        elif args.command == "submit":
            result = submit(args.run_dir)
            print(f"Submitted Batch {result['batch_id']} (status: {result['status']})")
        elif args.command == "status":
            result = status(args.run_dir)
            print(f"Batch {result['batch_id']}: {result['status']}")
        else:
            result = fetch(args.input_dir, args.run_dir)
            print(
                f"Validated {result['valid']}/{result['expected']} requests; "
                f"{result['failed']} failed, {result['missing']} missing"
            )
            return 0 if result["valid"] == result["expected"] else 1
    except (OSError, ValueError, KeyError, TypeError, requests.RequestException) as error:
        print(f"Batch screening stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
