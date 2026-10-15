"""Split requirement lines into fragments that each describe one requirement."""

import random
from collections import defaultdict
from dataclasses import dataclass

from amc.jobs.analysis import Codebook, period_of, split_line


@dataclass(frozen=True, slots=True)
class Fragment:
    ad_id: int
    period: str
    line: str
    text: str
    lead: str = ""

    @property
    def full_text(self) -> str:
        """Fragment with the lead-in of its list (e.g. "Znajomość: ustawy o ...")."""
        return f"{self.lead}: {self.text}" if self.lead else self.text


def fragments_of(ad_id: int, published_at: str, required: str, optional: str, codebook: Codebook):
    """Fragments of all requirement lines except statutory boilerplate."""
    for line in (required + "\n" + optional).split("\n"):
        line = line.strip()
        if not line or codebook.boilerplate.search(line):
            continue
        lead, parts = split_line(line)
        for text in parts:
            yield Fragment(ad_id, period_of(published_at), line, text, lead)


def draw_fragments(
    fragments: list[Fragment], per_period: int, max_per_ad: int, seed: int
) -> list[Fragment]:
    """Random fragments, equal count per period, at most `max_per_ad` from any one ad."""
    rng = random.Random(seed)
    chosen: list[Fragment] = []
    for period in ("pre", "post"):
        pool = [f for f in fragments if f.period == period]
        rng.shuffle(pool)
        taken: defaultdict[int, int] = defaultdict(int)
        picked = []
        for fragment in pool:
            if len(picked) == per_period:
                break
            if taken[fragment.ad_id] < max_per_ad:
                taken[fragment.ad_id] += 1
                picked.append(fragment)
        chosen.extend(picked)
    rng.shuffle(chosen)
    return chosen
