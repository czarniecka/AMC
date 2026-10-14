"""Download ESCO skills (Polish) to data/esco/esco_skills_pl.csv."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.esco.fetch import fetch_all, save_csv  # noqa: E402
from amc.youtube.api_client import CollectionError  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "data/esco")
    parser.add_argument("--delay", type=float, default=1.0)
    options = parser.parse_args()
    try:
        skills = fetch_all(options.output, delay=options.delay)
    except CollectionError as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1) from None
    save_csv(options.output / "esco_skills_pl.csv", skills)
    print(f"Saved {len(skills)} skills.")
