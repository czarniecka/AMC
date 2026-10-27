"""Screen prepared YouTube comment groups with concurrent Responses API calls."""

import argparse
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.youtube.screening_direct import run  # noqa: E402


def main() -> int:
    load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit-requests", type=int)
    parser.add_argument("--retry-failed", action="store_true")
    parser.add_argument(
        "--recover-only", action="store_true", help="Recover saved raw responses without API calls"
    )
    args = parser.parse_args()
    try:
        report = run(
            args.request_dir,
            args.output_dir,
            workers=args.workers,
            limit_requests=args.limit_requests,
            retry_failed=args.retry_failed,
            recover_only=args.recover_only,
        )
    except (OSError, ValueError, requests.RequestException) as error:
        parser.exit(2, f"Direct screening stopped: {error}\n")
    print(f"Validated {report['valid']}/{report['expected']} groups; {report['pending']} pending")
    return 0 if report["pending"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
