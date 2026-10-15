"""Compare codebook regexes with the hand-labeled fragments (precision/recall per category).

Uses the same fragment decision as the analysis (`fragment_decision`), so the figures
describe the instrument that produces the reported numbers.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from amc.jobs.analysis import Codebook, fragment_decision  # noqa: E402


def read_labels(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def read_texts(path: Path) -> dict[str, str]:
    """Fragment text with its list lead-in, as the analysis sees it, keyed by frag_id."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return {row["frag_id"]: row["full_text"] for row in csv.DictReader(stream)}


def evaluate(codebook: Codebook, rows: list[dict], texts: dict[str, str]):
    """Per-category counts over competence fragments, plus the formal/competence split."""
    counts = {name: [0, 0, 0] for name in codebook.skills}  # tp, fp, fn
    split = {"formal_hit": 0, "formal_total": 0, "competence_dropped": 0, "competence_total": 0}
    for row in rows:
        kind, found = fragment_decision(codebook, row["context_line"], texts[row["frag_id"]])
        gold = (
            {c for c in row["categories"].split(";") if c and c != "none"}
            if row["type"] == "competence"
            else set()
        )
        if row["type"] == "formal":
            split["formal_total"] += 1
            split["formal_hit"] += kind != "skill"
        if row["type"] == "competence":
            split["competence_total"] += 1
            split["competence_dropped"] += kind != "skill"
        for name, tally in counts.items():
            tally[0] += name in found and name in gold
            tally[1] += name in found and name not in gold
            tally[2] += name not in found and name in gold
    return counts, split


def ratio(a: int, b: int) -> float:
    return a / b if b else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sheet", type=Path, default=ROOT / "data/jobs/labeling/label_sheet.csv")
    parser.add_argument("--key", type=Path, default=ROOT / "data/jobs/labeling/label_key.csv")
    parser.add_argument("--codebook", type=Path, default=ROOT / "config/jobs/skill_codebook.json")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/jobs/analysis/codebook_validation.csv"
    )
    args = parser.parse_args()
    codebook, rows = Codebook.load(args.codebook), read_labels(args.sheet)
    version = json.loads(args.codebook.read_text(encoding="utf-8")).get("version", "")
    for row in rows:
        if row["type"] not in {"competence", "formal", "other"}:
            raise SystemExit(f"{row['frag_id']}: invalid type {row['type']!r}")
    counts, split = evaluate(codebook, rows, read_texts(args.key))
    print(f"codebook version {version}, {len(rows)} fragments")
    print(
        f"formal fragments caught by boilerplate/formal filter: "
        f"{split['formal_hit']}/{split['formal_total']}; "
        f"competences wrongly dropped by it: "
        f"{split['competence_dropped']}/{split['competence_total']}"
    )
    print(f"{'category':24}{'gold':>5}{'tp':>5}{'fp':>5}{'fn':>5}{'prec':>7}{'rec':>7}")
    output = []
    for name, (tp, fp, fn) in counts.items():
        precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
        print(f"{name:24}{tp + fn:>5}{tp:>5}{fp:>5}{fn:>5}{precision:>7.2f}{recall:>7.2f}")
        output.append([version, name, tp + fn, tp, fp, fn, precision, recall])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(
            ["codebook_version", "category", "gold", "tp", "fp", "fn", "precision", "recall"]
        )
        writer.writerows(output)


if __name__ == "__main__":
    main()
