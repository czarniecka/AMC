"""Embedding index of ESCO labels and nearest-skill search."""

import csv
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from amc.esco.embedder import Embedder

CHUNK = 1000
QUERY_BLOCK = 256


@dataclass(frozen=True, slots=True)
class Entry:
    uri: str
    label: str
    kind: str  # "preferred" or "alt"


@dataclass(frozen=True, slots=True)
class Match:
    uri: str
    label: str
    score: float
    kind: str


def read_skills(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def entries_of(skills: Sequence[dict[str, str]]) -> list[Entry]:
    """One entry for the preferred label and one per alternative label."""
    entries = []
    for skill in sorted(skills, key=lambda s: s["uri"]):
        entries.append(Entry(skill["uri"], skill["preferred_label"], "preferred"))
        for alt in filter(None, (a.strip() for a in skill["alt_labels"].split(" | "))):
            entries.append(Entry(skill["uri"], alt, "alt"))
    return entries


class Index:
    def __init__(self, entries: list[Entry], vectors: np.ndarray) -> None:
        self.entries, self.vectors = entries, vectors

    def top_k(self, queries: np.ndarray, k: int = 3) -> list[list[Match]]:
        """Best entry per skill for each query, highest cosine first."""
        results: list[list[Match]] = []
        width = min(len(self.entries), k * 8)
        for start in range(0, len(queries), QUERY_BLOCK):
            scores = queries[start : start + QUERY_BLOCK] @ self.vectors.T
            for row in scores:
                best = np.argpartition(-row, width - 1)[:width]
                seen: dict[str, Match] = {}
                for position in best[np.argsort(-row[best])]:
                    entry = self.entries[position]
                    if entry.uri not in seen:
                        seen[entry.uri] = Match(
                            entry.uri, entry.label, float(row[position]), entry.kind
                        )
                    if len(seen) == k:
                        break
                results.append(list(seen.values()))
        return results


def _directory(root: Path, model: str) -> Path:
    return root / "index" / re.sub(r"[^\w.-]", "_", model)


def build_index(
    skills_csv: Path,
    root: Path,
    embedder: Embedder,
    log: Callable[[str], None] = print,
) -> Index:
    """Embed every label; completed chunks are kept so an interrupted build resumes."""
    entries = entries_of(read_skills(skills_csv))
    directory = _directory(root, embedder.name)
    directory.mkdir(parents=True, exist_ok=True)
    meta = {"model": embedder.name, "entries": len(entries), "first": entries[0].uri}
    meta_path = directory / "meta.json"
    if meta_path.exists() and json.loads(meta_path.read_text(encoding="utf-8")) != meta:
        raise ValueError(f"{meta_path} describes a different skill list; remove it deliberately.")
    meta_path.write_text(json.dumps(meta), encoding="utf-8")
    parts = []
    for number, start in enumerate(range(0, len(entries), CHUNK)):
        path = directory / f"chunk_{number:04d}.npy"
        if not path.exists():
            texts = [entry.label for entry in entries[start : start + CHUNK]]
            np.save(path, embedder.embed(texts))
        parts.append(np.load(path))
        log(f"{min(start + CHUNK, len(entries))}/{len(entries)} labels embedded")
    return Index(entries, np.vstack(parts))


def load_index(skills_csv: Path, root: Path, model: str) -> Index:
    """Load a finished index; fail clearly when it was never built."""
    directory = _directory(root, model)
    meta_path = directory / "meta.json"
    if not meta_path.exists():
        raise FileNotFoundError(f"No index for {model}; run the build-index command first.")
    entries = entries_of(read_skills(skills_csv))
    if json.loads(meta_path.read_text(encoding="utf-8"))["entries"] != len(entries):
        raise ValueError("The skill list changed since the index was built; rebuild it.")
    chunks = sorted(directory.glob("chunk_*.npy"))
    return Index(entries, np.vstack([np.load(path) for path in chunks]))
