"""Command-line entry point for the YouTube collector."""

import argparse
import logging
import sqlite3
import sys
from pathlib import Path

from amc.youtube.api_client import CollectionError, YouTubeAPIClient
from amc.youtube.collector import CollectorConfig, YouTubeDataCollector
from amc.youtube.models import DEFAULT_QUERIES, SearchQuery


def main(argv: list[str] | None = None) -> int:
    """Run collection; return 0 on success, 1 on partial output, or 2 on setup errors."""
    parser = argparse.ArgumentParser(description="Collect YouTube videos and top-level comments")
    parser.add_argument("--query-pl", action="append", default=[], help="Polish phrase; repeatable")
    parser.add_argument(
        "--query-en", action="append", default=[], help="English phrase; repeatable"
    )
    parser.add_argument("--published-after", default="2023-01-01T00:00:00Z")
    parser.add_argument("--candidates-per-query", type=int, default=50)
    parser.add_argument("--max-videos", type=int, default=20)
    parser.add_argument("--max-comments", type=int, default=1000)
    parser.add_argument(
        "--video-id",
        action="append",
        default=[],
        help="Collect only this cached video without searching; repeatable",
    )
    parser.add_argument("--max-api-requests", type=int, default=200)
    parser.add_argument(
        "--with-transcripts", action="store_true", help="Fetch optional pl/en captions"
    )
    parser.add_argument("--output-dir", type=Path, default=Path("data/youtube"))
    parser.add_argument("--comment-order", choices=["relevance", "time"], default="relevance")
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Save all candidate metadata without fetching comments or captions",
    )
    parser.add_argument(
        "--refresh-comments",
        action="store_true",
        help="Revisit completed video samples; stored duplicates will not be added",
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    queries = (
        tuple(
            [SearchQuery(text, "pl") for text in args.query_pl]
            + [SearchQuery(text, "en") for text in args.query_en]
        )
        or DEFAULT_QUERIES
    )
    client = None
    try:
        config = CollectorConfig(
            queries=queries,
            published_after=args.published_after,
            candidates_per_query=args.candidates_per_query,
            max_videos=args.max_videos,
            max_comments=args.max_comments,
            include_transcripts=args.with_transcripts,
            output_dir=args.output_dir,
            refresh_comments=args.refresh_comments,
            comment_order=args.comment_order,
            discover_only=args.discover_only,
            video_ids=tuple(args.video_id),
        )
        client = YouTubeAPIClient(max_requests=args.max_api_requests)
        result = YouTubeDataCollector(client, config).collect()
    except (CollectionError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except OSError:
        print(
            "Cannot write CSV exports; check output directory access and open files.",
            file=sys.stderr,
        )
        return 2
    except sqlite3.Error:
        print(
            "Cannot access collection database; check its location and available space.",
            file=sys.stderr,
        )
        return 2
    except KeyboardInterrupt:
        print(
            "Collection interrupted; completed records were exported where possible.",
            file=sys.stderr,
        )
        return 130
    finally:
        if client is not None:
            client.close()
    print(
        f"Added {len(result.comments)} new comments. "
        f"Cumulative exports: {result.total_videos} videos, {result.total_comments} comments. "
        f"API requests: {client.request_count}."
    )
    return 1 if result.stopped_reason else 0


if __name__ == "__main__":
    raise SystemExit(main())
