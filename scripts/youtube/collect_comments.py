"""Collect comments from a configurable reviewed video selection."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.youtube.__main__ import main  # noqa: E402
from amc.youtube.selection import load_selection  # noqa: E402

if __name__ == "__main__":
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument(
        "--selection",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "config/youtube/approved_videos.json",
    )
    options, remaining = parser.parse_known_args()
    try:
        ids, limit = load_selection(options.selection)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(2) from None
    arguments = ["--max-comments", str(limit), "--max-videos", str(len(ids))]
    for video_id in ids:
        arguments.extend(["--video-id", video_id])
    raise SystemExit(main([*arguments, *remaining]))
