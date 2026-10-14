"""Skill-scope analysis: codebook flags per advertisement and small-sample comparisons."""

import json
import math
import random
import re
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path

CUTOFF = date(2023, 1, 1)
INSTITUTION_GROUPS = (
    ("veterinary", r"weterynar"),
    ("police", r"policj"),
    ("tax_customs", r"skarbow|administracji skarbowej|\bkas\b|celno"),
    (
        "ministry_central",
        r"ministerstw|kancelari|główny urząd|urząd (do spraw|komunikacji|zamówień)",
    ),
)


@dataclass(frozen=True, slots=True)
class Codebook:
    boilerplate: re.Pattern
    formal: re.Pattern
    skills: dict[str, re.Pattern]

    @classmethod
    def load(cls, path: Path) -> "Codebook":
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            re.compile("|".join(data["boilerplate"]), re.I),
            re.compile("|".join(data["formal"]), re.I),
            {name: re.compile(pattern, re.I) for name, pattern in data["skills"].items()},
        )


@dataclass(frozen=True, slots=True)
class AdFlags:
    ad_id: int
    window: str
    period: str
    group: str
    n_items: int
    categories: frozenset[str]


def period_of(published_at: str) -> str:
    return "pre" if date.fromisoformat(published_at) < CUTOFF else "post"


def institution_group(institution: str, unit: str) -> str:
    text = f"{institution} {unit}".lower()
    for name, pattern in INSTITUTION_GROUPS:
        if re.search(pattern, text):
            return name
    return "other"


def flag_ad(codebook: Codebook, required: str, optional: str) -> tuple[int, frozenset[str]]:
    """Count substantive requirement lines and the skill categories they mention."""
    lines = [line for line in (required + "\n" + optional).split("\n") if line.strip()]
    lines = [line for line in lines if not codebook.boilerplate.search(line)]
    skill_lines = [line for line in lines if not codebook.formal.search(line)]
    found = {
        name
        for name, pattern in codebook.skills.items()
        if any(pattern.search(line) for line in skill_lines)
    }
    return len(skill_lines), frozenset(found)


def fisher_exact(a: int, b: int, c: int, d: int) -> float:
    """Two-sided Fisher exact test for the table [[a, b], [c, d]]."""
    row1, col1, total = a + b, a + c, a + b + c + d

    def probability(x: int) -> float:
        return math.comb(col1, x) * math.comb(total - col1, row1 - x) / math.comb(total, row1)

    observed = probability(a)
    low, high = max(0, row1 - (total - col1)), min(row1, col1)
    return min(
        1.0, sum(p for x in range(low, high + 1) if (p := probability(x)) <= observed * (1 + 1e-9))
    )


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values."""
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted, running = {}, 0.0
    for rank, (name, p) in enumerate(ordered):
        running = max(running, min(1.0, p * (len(ordered) - rank)))
        adjusted[name] = running
    return adjusted


def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else float("nan")


def permutation_test(
    values: Sequence[float],
    labels: Sequence[str],
    strata: Sequence[str],
    *,
    iterations: int = 10000,
    seed: int = 1,
) -> float:
    """Two-sided p for the post-minus-pre mean difference, permuting labels within strata."""

    def difference(assigned: Sequence[str]) -> float:
        return mean([v for v, lab in zip(values, assigned, strict=True) if lab == "post"]) - mean(
            [v for v, lab in zip(values, assigned, strict=True) if lab == "pre"]
        )

    observed = abs(difference(labels))
    members = defaultdict(list)
    for index, stratum in enumerate(strata):
        members[stratum].append(index)
    rng, extreme = random.Random(seed), 0
    for _ in range(iterations):
        shuffled = list(labels)
        for indexes in members.values():
            group = [labels[i] for i in indexes]
            rng.shuffle(group)
            for i, label in zip(indexes, group, strict=True):
                shuffled[i] = label
        extreme += abs(difference(shuffled)) >= observed - 1e-12
    return (extreme + 1) / (iterations + 1)


def bootstrap_ci(
    pre: Sequence[float], post: Sequence[float], *, iterations: int = 5000, seed: int = 1
) -> tuple[float, float]:
    """95% percentile bootstrap interval for the post-minus-pre mean difference."""
    rng = random.Random(seed)
    diffs = sorted(
        mean(rng.choices(post, k=len(post))) - mean(rng.choices(pre, k=len(pre)))
        for _ in range(iterations)
    )
    return diffs[int(0.025 * iterations)], diffs[int(0.975 * iterations)]
