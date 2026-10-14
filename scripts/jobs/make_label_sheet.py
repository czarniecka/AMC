"""Create a blind hand-labeling sheet of requirement fragments (equal count per period)."""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.jobs.analysis import Codebook  # noqa: E402
from amc.jobs.fragments import draw_fragments, fragments_of  # noqa: E402
from amc.jobs.storage import JobStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
SHEET = ("frag_id", "fragment", "context_line", "type", "categories", "note")
KEY = ("frag_id", "ad_id", "period", "full_text")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data/jobs")
    parser.add_argument("--codebook", type=Path, default=ROOT / "config/jobs/skill_codebook.json")
    parser.add_argument("--count", type=int, default=150, help="total fragments (split evenly)")
    parser.add_argument("--max-per-ad", type=int, default=3)
    parser.add_argument("--seed", type=int, default=2026)
    options = parser.parse_args(argv)
    out = options.data / "labeling"
    sheet_path = out / "label_sheet.csv"
    if sheet_path.exists():
        print(f"{sheet_path} already exists; it may hold labels, so it is not overwritten.")
        return 1
    codebook = Codebook.load(options.codebook)
    store = JobStore(options.data)
    try:
        fragments = [
            fragment
            for ad in store.ads.values()
            for fragment in fragments_of(
                ad.ad_id,
                ad.published_at,
                store.texts[ad.ad_id].requirements_required,
                store.texts[ad.ad_id].requirements_optional,
                codebook,
            )
        ]
    finally:
        store.close()
    chosen = draw_fragments(fragments, options.count // 2, options.max_per_ad, options.seed)
    out.mkdir(exist_ok=True)
    with sheet_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(SHEET)
        for number, item in enumerate(chosen, 1):
            writer.writerow([f"F{number:03d}", item.text, item.line, "", "", ""])
    with (out / "label_key.csv").open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(KEY)
        for number, item in enumerate(chosen, 1):
            writer.writerow([f"F{number:03d}", item.ad_id, item.period, item.full_text])
    print(f"Wrote {len(chosen)} fragments to {sheet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
