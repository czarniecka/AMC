"""Prepare blind samples, adjudicate labels or evaluate predictions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.youtube.validation import main  # noqa: E402

if __name__ == "__main__":
    main()
