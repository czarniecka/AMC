"""Collect all KPRM advertisements in an ID range in the RepOD dataset format."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.jobs.client import KPRMClient  # noqa: E402
from amc.jobs.full import check_robots, collect_range  # noqa: E402
from amc.youtube.api_client import CollectionError  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=int, required=True, help="first advertisement ID")
    parser.add_argument("--end", type=int, required=True, help="last advertisement ID")
    parser.add_argument("--step", type=int, default=1)
    parser.add_argument("--output", type=Path, default=ROOT / "data/jobs/kprm_2024_2026.csv")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between requests")
    parser.add_argument("--limit", type=int, help="check at most this many IDs")
    options = parser.parse_args(argv)
    if options.delay < 1 or options.step < 1:
        parser.error("--delay must be at least 1 second and --step positive")
    client = KPRMClient(None, delay=options.delay, jitter=1.0)
    try:
        check_robots()
        collect_range(
            client,
            options.output,
            range(options.start, options.end + 1, options.step),
            options.limit,
        )
    except CollectionError as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Saved advertisements are retained; rerun to resume.")
        return 130
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
