"""Stage 2 labels (stance, attitude, threat_type, competence_claim, sector) via CLARIN-PL.

Input: texts that stage 1 labelled ai=yes and work=yes, by default wykop_ai_work.csv from
export_ai_work.py. Output: wykop_stage2.csv, resumable like stage 1.
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv  # noqa: E402

from amc.classification import job_concern_details  # noqa: E402
from amc.classification.clarin import ClarinClient, ClarinError  # noqa: E402
from amc.jobs.client import DEFAULT_USER_AGENT  # noqa: E402
from amc.wykop.classification import STAGE2_COLUMNS, run  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL = "deepseek-v4-flash-0731"


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/wykop/wykop_ai_work.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/wykop/wykop_stage2.csv")
    parser.add_argument(
        "--model", help=f"CLARIN-PL model (default: CLARIN_MODEL or {DEFAULT_MODEL})"
    )
    parser.add_argument("--workers", type=int, default=8, help="parallel requests")
    parser.add_argument("--limit", type=int, help="classify at most this many texts")
    parser.add_argument("--list-models", action="store_true", help="print available models")
    options = parser.parse_args(argv)
    try:
        client = ClarinClient(
            os.getenv("CLARIN_TOKEN", ""),
            user_agent=os.getenv("AMC_USER_AGENT") or DEFAULT_USER_AGENT,
        )
        if options.list_models:
            print("\n".join(client.models()))
            return 0
        model = options.model or os.getenv("CLARIN_MODEL") or DEFAULT_MODEL
        run(
            job_concern_details.ClarinClassifier(client),
            options.input,
            options.output,
            model,
            columns=STAGE2_COLUMNS,
            prompt_hash=job_concern_details.PROMPT_HASH,
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
