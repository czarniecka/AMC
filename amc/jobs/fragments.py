"""Split requirement lines into fragments that each describe one requirement."""

import random
import re
from collections import defaultdict
from dataclasses import dataclass

from amc.jobs.analysis import Codebook, period_of

SPLIT = re.compile(r"\s*[;,]\s+|\s*;\s*|\s*,$")
MIN_LENGTH = 4


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


def split_line(line: str) -> tuple[str, list[str]]:
    """Return the lead-in before an early colon and the comma/semicolon-separated parts.

    Commas inside numbers like 1,5 are kept because a space must follow the separator.
    """
    lead, body = "", line
    colon = line.find(":")
    if 0 < colon <= 60:
        lead, body = line[:colon].strip(), line[colon + 1 :]
    parts = (part.strip(" .:-\u2013\u00ad\t") for part in SPLIT.split(body))
    return lead, [part for part in parts if len(part) >= MIN_LENGTH]


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
