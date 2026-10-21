"""Add comments to Wykop entries already saved; split work between people by --start/--end."""

import argparse
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.wykop.collector import collect_comments  # noqa: E402
from amc.wykop.selection import load_selection  # noqa: E402
from amc.wykop.settings import connect  # noqa: E402
from amc.youtube.api_client import CollectionError  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=ROOT / "config/wykop/collection.json")
    parser.add_argument("--tags", nargs="+", help="override the configured tags")
    parser.add_argument("--start", type=date.fromisoformat, help="override the configured start")
    parser.add_argument("--end", type=date.fromisoformat, default=date.today())
    parser.add_argument("--output", type=Path, default=ROOT / "data/wykop/wykop_entries.csv")
    parser.add_argument("--min-upvotes", type=int, help="override comments.min_upvotes")
    parser.add_argument("--first", type=int, help="override comments.first")
    parser.add_argument("--limit", type=int, help="process at most this many entries")
    options = parser.parse_args(argv)
    try:
        selection = load_selection(options.config)
        client, rows = connect(ROOT / ".env")
        try:
            collect_comments(
                client,
                rows,
                options.output,
                options.tags or selection.tags,
                options.start or selection.start,
                options.end,
                selection.min_upvotes if options.min_upvotes is None else options.min_upvotes,
                options.first or selection.first,
                options.limit,
            )
        finally:
            client.close()
    except (CollectionError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Interrupted. Saved comments are retained; rerun to resume.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
