"""Collect top-level comments of monthly "Ask HN: Who is hiring?" threads, one row per ad.

The ad list comes from the thread's Firebase `kids` field and the texts from one HN Search
tree request. Comments missing from the tree are checked in Firebase, so deleted and dead
comments are skipped exactly. Rows are appended; threads of past months that finished are
listed in `<name>_threads.txt` and are not requested again.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path

from amc.csv_files import append_rows, read_rows
from amc.hn.client import HNClient
from amc.hn.parser import COLUMNS, ad_row

MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
TITLE = re.compile(r"Ask HN: Who is hiring\?", re.I)


@dataclass(frozen=True, slots=True)
class Thread:
    thread_id: int
    month: str  # YYYY-MM from the title
    created: int


def month_start(month: str, shift: int = 0) -> int:
    """Unix time of the first day of YYYY-MM shifted by `shift` months."""
    year, number = map(int, month.split("-"))
    year, number = year + (number - 1 + shift) // 12, (number - 1 + shift) % 12 + 1
    return int(datetime(year, number, 1, tzinfo=timezone.utc).timestamp())


def thread_month(title: str, created: int) -> str:
    match = re.search(r"\((\w+)\s+(\d{4})\)", title)
    if match and match.group(1).lower() in MONTHS:
        return f"{match.group(2)}-{MONTHS.index(match.group(1).lower()) + 1:02d}"
    return datetime.fromtimestamp(created, timezone.utc).strftime("%Y-%m")


def find_threads(client: HNClient, first: str, last: str) -> list[Thread]:
    """'Who is hiring?' threads from `first` to `last` month (YYYY-MM), oldest first.

    'Who wants to be hired?' and 'Freelancer?' threads are skipped.
    """
    hits = client.threads(month_start(first), month_start(last, 1))
    threads = [
        Thread(
            int(hit["objectID"]),
            thread_month(hit["title"], hit["created_at_i"]),
            hit["created_at_i"],
        )
        for hit in hits
        if TITLE.match(hit["title"])
    ]
    return sorted(threads, key=lambda thread: thread.created)


def thread_ads(client: HNClient, thread: Thread) -> tuple[list[dict], int] | None:
    """Rows and the number of skipped deleted or dead comments; None if the thread failed."""
    item = client.item(thread.thread_id)
    if item is None:
        return None
    texts = {child["id"]: child for child in client.tree(thread.thread_id).get("children", [])}
    rows, skipped = [], 0
    for kid in item.get("kids", []):
        child = texts.get(kid)
        if child and child.get("text"):
            created, html = child["created_at_i"], child["text"]
        else:
            comment = client.item(kid)
            if comment is None:
                return None
            if comment.get("deleted") or comment.get("dead") or not comment.get("text"):
                skipped += 1
                continue
            created, html = comment["time"], comment["text"]
        rows.append(ad_row(kid, thread.thread_id, thread.month, created, html))
    return rows, skipped


def threads_path(output: Path) -> Path:
    return output.with_name(output.stem + "_threads.txt")


def collect(
    client: HNClient,
    output: Path,
    first: str,
    last: str,
    limit: int | None = None,
    log: Callable[[str], None] = print,
) -> int:
    """Append new ads of threads not finished before; returns the number of new rows."""
    saved = {int(row["ad_id"]) for row in read_rows(output, COLUMNS)}
    finished_path = threads_path(output)
    finished = set(map(int, finished_path.read_text().split())) if finished_path.exists() else set()
    threads = find_threads(client, first, last)
    todo = [thread for thread in threads if thread.thread_id not in finished][:limit]
    log(f"Threads in range: {len(threads)}, to fetch: {len(todo)}, saved ads: {len(saved)}")
    current = date.today().strftime("%Y-%m")
    total = 0
    with (
        append_rows(output, COLUMNS) as (stream, writer),
        finished_path.open("a", encoding="utf-8") as finished_log,
    ):
        for n, thread in enumerate(todo, 1):
            result = thread_ads(client, thread)
            if result is None:
                log(f"[{n}/{len(todo)}] {thread.month}: thread {thread.thread_id} failed, skipped")
                continue
            rows, skipped = result
            new = [row for row in rows if row["ad_id"] not in saved]
            writer.writerows(new)
            stream.flush()
            saved.update(row["ad_id"] for row in new)
            total += len(new)
            # The current month's thread keeps growing, so it is fetched again next time.
            if thread.month < current:
                finished_log.write(f"{thread.thread_id}\n")
                finished_log.flush()
            progress = f"[{n}/{len(todo)}] {thread.month}"
            log(f"{progress}: {len(rows)} ads, {len(new)} new, {skipped} skipped")
    log(f"Saved {total} new advertisements.")
    return total
