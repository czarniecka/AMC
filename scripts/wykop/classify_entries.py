"""Classify Wykop entries and comments with the H1 labels, using a local Ollama model."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from amc.classification.job_concern import OllamaClient  # noqa: E402
from amc.wykop.classification import run  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/wykop/wykop_entries.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/wykop/wykop_classified.csv")
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    parser.add_argument(
        "--workers", type=int, default=2, help="parallel requests (match OLLAMA_NUM_PARALLEL)"
    )
    parser.add_argument("--limit", type=int, help="classify at most this many texts")
    options = parser.parse_args(argv)
    try:
        run(
            OllamaClient(),
            options.input,
            options.output,
            options.model,
            workers=options.workers,
            limit=options.limit,
        )
    except requests.RequestException as error:
        # Ollama's error body names the cause (missing model, memory); it holds no post text.
        detail = error.response.text[:300] if error.response is not None else ""
        print(
            f"Ollama request failed: {type(error).__name__}: {error} {detail}\n"
            f"Check that Ollama runs at {os.getenv('OLLAMA_BASE_URL')} and that the model "
            "is installed. Saved predictions are retained; rerun to resume.",
            file=sys.stderr,
        )
        return 1
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Saved predictions are retained; rerun to resume.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
