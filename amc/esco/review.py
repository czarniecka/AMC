"""Second-pass review sheet: judge ESCO proposals, then read the verdicts for calibration."""

import csv
from collections.abc import Sequence
from pathlib import Path

from amc.esco.index import Match

SHEET = (
    "frag_id",
    "fragment",
    "context_line",
    "candidate_1",
    "candidate_2",
    "candidate_3",
    "best",
    "note",
)
KEY = ("frag_id", "rank", "uri", "score")
VERDICTS = {"1", "2", "3", "none"}
DESCRIPTION_LENGTH = 160


def candidate_cell(match: Match, description: str) -> str:
    text = (
        description
        if len(description) <= DESCRIPTION_LENGTH
        else description[:DESCRIPTION_LENGTH] + "..."
    )
    return f"{match.label} - {text}" if text else match.label


def _write(path: Path, header: Sequence[str], rows: Sequence[Sequence]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def write_review(
    sheet_path: Path,
    key_path: Path,
    items: Sequence[tuple[str, str, str, list[Match]]],
    descriptions: dict[str, str],
) -> None:
    """items: (frag_id, fragment, context_line, top matches). Scores stay out of the sheet."""
    if sheet_path.exists():
        raise FileExistsError(f"{sheet_path} exists and may hold verdicts; not overwritten.")
    rows, keys = [], []
    for frag_id, fragment, context, matches in items:
        cells = [candidate_cell(m, descriptions.get(m.uri, "")) for m in matches]
        cells += [""] * (3 - len(cells))
        rows.append([frag_id, fragment, context, *cells, "", ""])
        keys.extend([frag_id, rank, m.uri, f"{m.score:.6f}"] for rank, m in enumerate(matches, 1))
    _write(sheet_path, SHEET, rows)
    _write(key_path, KEY, keys)


def read_verdicts(sheet_path: Path, key_path: Path) -> tuple[list[float], list[bool], int, int]:
    """Top-1 scores, whether top-1 was judged correct, count of top-3 hits, reviewed count."""
    with key_path.open(encoding="utf-8-sig", newline="") as stream:
        top1 = {r["frag_id"]: float(r["score"]) for r in csv.DictReader(stream) if r["rank"] == "1"}
    with sheet_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream))
    scores, correct, hits = [], [], 0
    for row in rows:
        verdict = row["best"].strip().lower()
        if verdict not in VERDICTS:
            raise ValueError(f"{row['frag_id']}: 'best' must be one of 1, 2, 3, none.")
        if row["frag_id"] not in top1:
            continue  # no proposal was available for this fragment
        scores.append(top1[row["frag_id"]])
        correct.append(verdict == "1")
        hits += verdict != "none"
    return scores, correct, hits, len(scores)
