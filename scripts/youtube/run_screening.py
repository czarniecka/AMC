"""Label H1 screening batches with a local Ollama model; resumable and validated."""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import requests  # noqa: E402
from dotenv import load_dotenv  # noqa: E402

from amc.youtube.screening_run import OllamaChat, default_base_url, merge, run  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--screening-dir", type=Path, required=True)
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    parser.add_argument("--base-url", default=default_base_url())
    parser.add_argument("--limit", type=int, help="label at most this many batches in this run")
    parser.add_argument("--max-retries", type=int, default=3)
    parser.add_argument(
        "--min-split", type=int, default=10, help="smallest split of a failing batch"
    )
    parser.add_argument("--num-ctx", type=int, default=16384, help="model context window (tokens)")
    parser.add_argument("--merge-only", action="store_true", help="only rebuild labels.csv")
    options = parser.parse_args(argv)
    directory = options.screening_dir
    if not (directory / "batches.jsonl").exists():
        parser.error(f"{directory} has no batches.jsonl")
    try:
        if not options.merge_only:
            counts = run(
                directory,
                OllamaChat(options.base_url, options.model, num_ctx=options.num_ctx),
                options.model,
                max_retries=options.max_retries,
                min_split=options.min_split,
                limit=options.limit,
                log=lambda message: print(message, flush=True),
            )
            print(f"Batches: {counts}")
        print(f"Merged: {merge(directory)}")
    except requests.RequestException as error:
        print(
            f"Ollama request failed: {type(error).__name__}: {error}\n"
            f"Check that Ollama runs at {options.base_url} and has {options.model}. "
            "Saved results are kept; rerun to resume.",
            file=sys.stderr,
        )
        return 1
    except (OSError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Saved results are kept; rerun to resume.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
