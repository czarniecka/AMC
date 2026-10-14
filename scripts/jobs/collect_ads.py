"""Sample and collect KPRM job advertisements for the AI-and-requirements study."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.jobs.client import KPRMClient  # noqa: E402
from amc.jobs.collector import build_sample, collect  # noqa: E402
from amc.jobs.sampling import PILOT_WINDOWS  # noqa: E402
from amc.jobs.storage import JobStore  # noqa: E402
from amc.youtube.api_client import CollectionError  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/jobs")
    parser.add_argument("--per-window", type=int, default=50)
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    parser.add_argument("--limit", type=int, help="process at most this many pending ads")
    parser.add_argument("--sample-only", action="store_true", help="only build the manifest")
    options = parser.parse_args(argv)
    if options.per_window < 1 or options.delay < 1:
        parser.error("--per-window must be positive and --delay at least 1 second")
    client = KPRMClient(options.output / "raw", delay=options.delay)
    try:
        store = JobStore(options.output)
        try:
            build_sample(store, client, PILOT_WINDOWS, options.per_window, options.seed)
            if not options.sample_only:
                collect(store, client, options.limit)
        finally:
            store.close()
    except CollectionError as error:
        print(str(error), file=sys.stderr)
        return 1
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
