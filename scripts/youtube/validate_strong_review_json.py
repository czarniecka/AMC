"""Validate one strong-review response against its versioned JSON input."""

import argparse
import json
from pathlib import Path

from import_strong_review import validate_answer


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    try:
        batch = json.loads(args.batch.read_text(encoding="utf-8"))
        answer = json.loads(args.response.read_text(encoding="utf-8"))
        if batch["batch_id"] != args.batch.stem:
            raise ValueError("Input filename does not match batch_id")
        ids = [comment["id"] for comment in batch["comments"]]
        validate_answer(answer, batch["batch_id"], ids)
    except (OSError, KeyError, ValueError, TypeError) as error:
        parser.exit(2, f"Validation failed: {error}\n")
    print(f"Valid {batch['batch_id']}: {len(ids)} labels")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
