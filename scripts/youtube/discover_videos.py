"""Discover candidate metadata without collecting comments."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.youtube.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["--discover-only", "--candidates-per-query", "250", *sys.argv[1:]]))
