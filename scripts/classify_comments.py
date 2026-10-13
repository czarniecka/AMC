"""Classify stored comments and resume previously completed work."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from amc.classification.batch_classifier import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
