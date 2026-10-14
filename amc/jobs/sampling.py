"""Reproducible stratified sample of advertisement IDs by publication window."""

import random
from bisect import bisect_left
from dataclasses import dataclass
from datetime import date

from amc.jobs.client import KPRMClient
from amc.jobs.parser import ParseError, parse_ad

# IDs grow with publication time. Measured anchors narrow the boundary search.
ANCHORS = (
    (90000, date(2021, 12, 29)),
    (100000, date(2022, 6, 2)),
    (110000, date(2022, 11, 8)),
    (120000, date(2023, 5, 2)),
    (130000, date(2023, 11, 14)),
    (140000, date(2024, 7, 9)),
    (150000, date(2025, 3, 26)),
    (160000, date(2026, 1, 27)),
)
FIRST_ID, LAST_ID = 70000, 170000
PROBE_GAP = 20


@dataclass(frozen=True, slots=True)
class Window:
    name: str
    start: date
    end: date  # inclusive


PILOT_WINDOWS = (
    Window("2021-H2", date(2021, 7, 1), date(2021, 12, 31)),
    Window("2022-H1", date(2022, 1, 1), date(2022, 6, 30)),
    Window("2023-H2", date(2023, 7, 1), date(2023, 12, 31)),
    Window("2025-H2", date(2025, 7, 1), date(2025, 12, 31)),
)


def published_on(client: KPRMClient, ad_id: int) -> tuple[int, date] | None:
    """Date of this ID or of the next existing one within PROBE_GAP IDs."""
    for candidate in range(ad_id, ad_id + PROBE_GAP):
        html = client.fetch_ad(candidate)
        if html is None:
            continue
        try:
            ad, _ = parse_ad(html)
        except ParseError:
            continue
        return candidate, date.fromisoformat(ad.published_at)
    return None


def first_id_on_or_after(client: KPRMClient, day: date) -> int:
    """Smallest ID published on or after `day`, found by binary search."""
    dates = [anchor_date for _, anchor_date in ANCHORS]
    index = bisect_left(dates, day)
    low = ANCHORS[index - 1][0] if index > 0 else FIRST_ID
    high = ANCHORS[index][0] if index < len(ANCHORS) else LAST_ID
    while low < high:
        middle = (low + high) // 2
        found = published_on(client, middle)
        if found is None or found[1] >= day:
            high = middle
        else:
            low = middle + 1
    return low


def id_range(client: KPRMClient, window: Window) -> range:
    """Half-open ID range covering the window."""
    first = first_id_on_or_after(client, window.start)
    after = first_id_on_or_after(client, date.fromordinal(window.end.toordinal() + 1))
    return range(first, after)


def draw(ids: range, count: int, seed: int) -> list[int]:
    """Deterministic sample without replacement, sorted for readable manifests."""
    return sorted(random.Random(seed).sample(ids, min(count, len(ids))))
