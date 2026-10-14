"""Map requirement fragments to ESCO skills with embeddings and calibrate the threshold.

Commands, in order:
  build-index    embed all ESCO labels (needs Ollama with the model installed)
  match          top-3 ESCO skills for every fragment of every collected ad
  review-sheet   proposals for hand-labeled competence fragments (second labeling pass)
  calibrate      precision/recall per threshold from the reviewed sheet
"""

import argparse
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.esco.calibration import best_threshold, threshold_table  # noqa: E402
from amc.esco.embedder import OllamaEmbedder  # noqa: E402
from amc.esco.index import build_index, load_index, read_skills  # noqa: E402
from amc.esco.review import read_verdicts, write_review  # noqa: E402
from amc.jobs.analysis import Codebook  # noqa: E402
from amc.jobs.fragments import fragments_of  # noqa: E402
from amc.jobs.storage import JobStore  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
TOP_K = 3


def write_csv(path: Path, header: list[str], rows: list[list]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("command", choices=["build-index", "match", "review-sheet", "calibrate"])
    parser.add_argument("--esco", type=Path, default=ROOT / "data/esco")
    parser.add_argument("--jobs", type=Path, default=ROOT / "data/jobs")
    parser.add_argument("--codebook", type=Path, default=ROOT / "config/jobs/skill_codebook.json")
    parser.add_argument(
        "--model", help="Ollama embedding model (default: ESCO_EMBED_MODEL or bge-m3)"
    )
    parser.add_argument("--min-precision", type=float, default=0.8)
    options = parser.parse_args(argv)
    skills_csv = options.esco / "esco_skills_pl.csv"
    embedder = OllamaEmbedder(options.model)
    review_dir = options.jobs / "labeling"

    if options.command == "build-index":
        build_index(skills_csv, options.esco, embedder)
        return 0

    if options.command == "calibrate":
        scores, correct, hits, total = read_verdicts(
            review_dir / "esco_review.csv", review_dir / "esco_review_key.csv"
        )
        rows = threshold_table(scores, correct)
        best = best_threshold(rows, options.min_precision)
        print(
            f"Reviewed {total}; top-1 correct {sum(correct) / total:.0%}; "
            f"top-3 hit {hits / total:.0%}"
        )
        print("threshold  accepted  precision  recall  f1")
        for row in rows[:: max(1, len(rows) // 15)]:
            print(
                f"  {row.threshold:.3f}    {row.accepted:4d}      {row.precision:.2f}"
                f"      {row.recall:.2f}  {row.f1:.2f}"
            )
        print(
            f"\nChosen threshold {best.threshold:.3f} (precision {best.precision:.2f}, "
            f"recall {best.recall:.2f}, F1 {best.f1:.2f})"
        )
        write_csv(
            options.jobs / "analysis/esco_threshold_table.csv",
            ["threshold", "accepted", "precision", "recall", "f1"],
            [[r.threshold, r.accepted, r.precision, r.recall, r.f1] for r in rows],
        )
        return 0

    index = load_index(skills_csv, options.esco, embedder.name)
    skills = {s["uri"]: s for s in read_skills(skills_csv)}

    if options.command == "match":
        codebook = Codebook.load(options.codebook)
        store = JobStore(options.jobs)
        try:
            fragments = [
                f
                for ad in sorted(store.ads.values(), key=lambda a: a.ad_id)
                for f in fragments_of(
                    ad.ad_id,
                    ad.published_at,
                    store.texts[ad.ad_id].requirements_required,
                    store.texts[ad.ad_id].requirements_optional,
                    codebook,
                )
            ]
        finally:
            store.close()
        matches = index.top_k(embedder.embed([f.full_text for f in fragments]), TOP_K)
        rows = [
            [
                f.ad_id,
                f.period,
                f.line,
                f.full_text,
                rank,
                m.uri,
                m.label,
                f"{m.score:.4f}",
                skills[m.uri]["group_code"],
            ]
            for f, found in zip(fragments, matches, strict=True)
            for rank, m in enumerate(found, 1)
        ]
        write_csv(
            options.jobs / "analysis/esco_matches.csv",
            ["ad_id", "period", "line", "text", "rank", "uri", "label", "score", "group_code"],
            rows,
        )
        print(f"Matched {len(fragments)} fragments.")
        return 0

    # review-sheet
    with (review_dir / "label_sheet.csv").open(encoding="utf-8-sig", newline="") as stream:
        sheet = list(csv.DictReader(stream))
    with (review_dir / "label_key.csv").open(encoding="utf-8-sig", newline="") as stream:
        full_text = {r["frag_id"]: r["full_text"] for r in csv.DictReader(stream)}
    unlabeled = [r["frag_id"] for r in sheet if not r["type"].strip()]
    if unlabeled:
        print(
            f"{len(unlabeled)} fragments have no type yet (first: {unlabeled[0]}). "
            "Finish labeling first."
        )
        return 1
    chosen = [r for r in sheet if r["type"].strip().lower() == "competence"]
    matches = index.top_k(embedder.embed([full_text[r["frag_id"]] for r in chosen]), TOP_K)
    items = [
        (r["frag_id"], r["fragment"], r["context_line"], found)
        for r, found in zip(chosen, matches, strict=True)
    ]
    write_review(
        review_dir / "esco_review.csv",
        review_dir / "esco_review_key.csv",
        items,
        {uri: s["description"] for uri, s in skills.items()},
    )
    print(f"Wrote review sheet for {len(items)} competence fragments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
