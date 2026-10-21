"""Collect job advertisements from monthly "Ask HN: Who is hiring?" threads."""

import argparse
import os
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv  # noqa: E402

from amc.hn.client import HNClient  # noqa: E402
from amc.hn.collector import collect  # noqa: E402
from amc.jobs.client import DEFAULT_USER_AGENT  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2019-01", help="first month, YYYY-MM")
    parser.add_argument("--end", default=date.today().strftime("%Y-%m"), help="last month, YYYY-MM")
    parser.add_argument("--output", type=Path, default=ROOT / "data/hn/hn_whoishiring.csv")
    parser.add_argument("--limit", type=int, help="fetch at most this many threads")
    options = parser.parse_args(argv)
    load_dotenv(ROOT / ".env", override=False)
    client = HNClient(user_agent=os.getenv("AMC_USER_AGENT", DEFAULT_USER_AGENT))
    try:
        collect(client, options.output, options.start, options.end, options.limit)
    except (ConnectionError, ValueError) as error:
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
