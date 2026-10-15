"""Compare codebook regexes with the hand-labeled fragments (precision/recall per category)."""

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from amc.jobs.analysis import Codebook  # noqa: E402


def read_labels(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def predicted(codebook: Codebook, text: str) -> tuple[str, set[str]]:
    """Return the codebook decision for one text: boilerplate, formal or skill categories."""
    if codebook.boilerplate.search(text):
        return "boilerplate", set()
    if codebook.formal.search(text):
        return "formal", set()
    return "skill", {name for name, rx in codebook.skills.items() if rx.search(text)}


def evaluate(codebook: Codebook, rows: list[dict], field: str):
    """Per-category counts over competence fragments, plus the formal/competence split."""
    counts = {name: [0, 0, 0] for name in codebook.skills}  # tp, fp, fn
    split = {"formal_hit": 0, "formal_total": 0, "competence_dropped": 0, "competence_total": 0}
    for row in rows:
        kind, found = predicted(codebook, row[field])
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
    parser.add_argument("--codebook", type=Path, default=ROOT / "config/jobs/skill_codebook.json")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "data/jobs/analysis/codebook_validation.csv"
    )
    args = parser.parse_args()
    codebook, rows = Codebook.load(args.codebook), read_labels(args.sheet)
    for row in rows:
        if row["type"] not in {"competence", "formal", "other"}:
            raise SystemExit(f"{row['frag_id']}: invalid type {row['type']!r}")
    output = []
    for field in ("fragment", "context_line"):
        counts, split = evaluate(codebook, rows, field)
        print(f"\n== regexes applied to {field} ==")
        print(
            f"formal fragments caught by boilerplate/formal filter: "
            f"{split['formal_hit']}/{split['formal_total']}; "
            f"competences wrongly dropped by it: "
            f"{split['competence_dropped']}/{split['competence_total']}"
        )
        print(f"{'category':24}{'gold':>5}{'tp':>5}{'fp':>5}{'fn':>5}{'prec':>7}{'rec':>7}")
        for name, (tp, fp, fn) in counts.items():
            precision, recall = ratio(tp, tp + fp), ratio(tp, tp + fn)
            print(f"{name:24}{tp + fn:>5}{tp:>5}{fp:>5}{fn:>5}{precision:>7.2f}{recall:>7.2f}")
            output.append([field, name, tp + fn, tp, fp, fn, precision, recall])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(["applied_to", "category", "gold", "tp", "fp", "fn", "precision", "recall"])
        writer.writerows(output)


if __name__ == "__main__":
    main()
