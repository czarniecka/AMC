"""Classify Wykop entries and comments like YouTube comments, using a CLARIN-PL model."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv  # noqa: E402

from amc.classification.clarin import ClarinClient, ClarinError  # noqa: E402
from amc.jobs.client import DEFAULT_USER_AGENT  # noqa: E402
from amc.wykop.classification import run  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/wykop/wykop_entries.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/wykop/wykop_classified.csv")
    parser.add_argument("--model", help="CLARIN-PL model (default: CLARIN_MODEL)")
    parser.add_argument("--workers", type=int, default=8, help="parallel requests")
    parser.add_argument("--limit", type=int, help="classify at most this many texts")
    parser.add_argument("--list-models", action="store_true", help="print available models")
    options = parser.parse_args(argv)
    load_dotenv(ROOT / ".env", override=False)
    try:
        client = ClarinClient(
            os.getenv("CLARIN_TOKEN", ""),
            user_agent=os.getenv("AMC_USER_AGENT", DEFAULT_USER_AGENT),
        )
        if options.list_models:
            print("\n".join(client.models()))
            return 0
        model = options.model or os.getenv("CLARIN_MODEL", "")
        if not model:
            parser.error("set CLARIN_MODEL in .env or pass --model")
        run(
            client,
            options.input,
            options.output,
            model,
            workers=options.workers,
            limit=options.limit,
        )
    except (ClarinError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Saved predictions are retained; rerun to resume.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
