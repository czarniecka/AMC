"""Collect a balanced English-language YouTube search sample or export Label Studio tasks."""

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.youtube.api_client import CollectionError, YouTubeAPIClient  # noqa: E402
from amc.youtube.random_sample import collect, export_label_studio  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / "data/youtube/work_sample_v3/sample.sqlite3"
DEFAULT_WORDS = ROOT / "config/youtube/work_queries.txt"


def status(database: Path) -> str:
    if not database.exists():
        return "No sample database yet."
    with sqlite3.connect(database) as connection:
        counts = dict(
            connection.execute(
                "SELECT comment_period,COUNT(*) FROM comments GROUP BY comment_period"
            )
        )
        searches = dict(connection.execute("SELECT period,COUNT(*) FROM searches GROUP BY period"))
        videos = dict(connection.execute("SELECT period,COUNT(*) FROM videos GROUP BY period"))
        columns = {row[1] for row in connection.execute("PRAGMA table_info(videos)")}
        rejected_column = "rejected_short" if "rejected_short" in columns else "rejected_likes"
        rejected_query = (
            "SELECT COALESCE(SUM(rejected_short),0),COALESCE(SUM(rejected_language),0) FROM videos"
            if rejected_column == "rejected_short"
            else "SELECT COALESCE(SUM(rejected_likes),0),"
            "COALESCE(SUM(rejected_language),0) FROM videos"
        )
        rejected = connection.execute(rejected_query).fetchone()
        rejected_reason = "short text" if rejected_column == "rejected_short" else "likes"
    return (
        f"Comments: pre_chatgpt={counts.get('pre_chatgpt', 0)}, "
        f"post_chatgpt={counts.get('post_chatgpt', 0)}. "
        f"Videos: {videos}. Searches: {searches}. "
        f"Rejected by {rejected_reason}: {rejected[0]}; by language: {rejected[1]}."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("collect", "status", "export"))
    parser.add_argument("--database", type=Path, default=DEFAULT_DB)
    parser.add_argument("--words", type=Path, default=DEFAULT_WORDS)
    parser.add_argument("--target", type=int, default=10000, help="minimum collected comments")
    parser.add_argument("--seed", type=int, default=20261025)
    parser.add_argument("--min-views", type=int, default=10000)
    parser.add_argument(
        "--min-comments", type=int, default=50, help="skip videos with fewer comments"
    )
    parser.add_argument("--min-chars", type=int, default=20)
    parser.add_argument("--videos-per-query", type=int, default=10)
    parser.add_argument("--max-api-requests", type=int, default=80)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/youtube/work_sample_v3/label_studio"
    )
    parser.add_argument("--export-batch-size", type=int, default=1000)
    parser.add_argument(
        "--export-count", type=int, help="number of comments to sample for labeling"
    )
    args = parser.parse_args(argv)
    if args.command == "status":
        print(status(args.database))
        return 0
    if args.command == "export":
        if not args.database.exists():
            parser.error("sample database does not exist")
        try:
            count = export_label_studio(
                args.database,
                args.output,
                args.export_batch_size,
                export_count=args.export_count,
                seed=args.seed,
            )
        except (OSError, ValueError, sqlite3.Error) as error:
            print(str(error), file=sys.stderr)
            return 2
        print(f"Exported {count} tasks to {args.output}")
        return 0
    client = None
    try:
        client = YouTubeAPIClient(max_requests=args.max_api_requests)
        counts = collect(
            client,
            args.database,
            args.words,
            target=args.target,
            seed=args.seed,
            min_views=args.min_views,
            min_comments=args.min_comments,
            min_chars=args.min_chars,
            videos_per_query=args.videos_per_query,
            progress=lambda message: print(message, flush=True),
        )
    except (CollectionError, OSError, ValueError, sqlite3.Error) as error:
        print(f"Collection stopped: {error}", file=sys.stderr)
        print(status(args.database))
        return 1
    except KeyboardInterrupt:
        print("Interrupted; completed pages are saved.", file=sys.stderr)
        print(status(args.database))
        return 130
    finally:
        if client:
            client.close()
    print(f"Target reached: {counts}. API requests this run: {client.request_count}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
