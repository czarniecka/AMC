"""Two-stage, resumable collection: entries by tag and month, then comments to saved entries.

Entries come 50 per request, while comments need one request per entry, so comments are a
separate stage. Rows are appended. Finished past months are listed in `<name>_months.txt`;
entries for which the API returned no comment with text are listed in `<name>_no_comments.txt`.
An entry with several selected tags is saved once, under the first tag that found it.
"""

import time
from collections.abc import Callable, Iterable, Iterator
from datetime import date
from pathlib import Path

from amc.csv_files import append_rows, read_rows
from amc.wykop.client import WykopClient
from amc.wykop.records import COLUMNS, COMMENT, ENTRY, RowBuilder, select_comments


def side_file(output: Path, suffix: str) -> Path:
    return output.with_name(f"{output.stem}_{suffix}.txt")


def months(start: date, end: date) -> Iterator[tuple[int, int]]:
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def collect_entries(
    client: WykopClient,
    rows: RowBuilder,
    output: Path,
    tags: Iterable[str],
    start: date,
    end: date,
    page_limit: int | None = None,
    log: Callable[[str], None] = print,
) -> int:
    """Append entries (without comments); returns the number of new entries."""
    saved = {row["entry_id"] for row in read_rows(output, COLUMNS) if row["type"] == ENTRY}
    months_path = side_file(output, "months")
    finished = (
        set(months_path.read_text(encoding="utf-8").split("\n")) if months_path.exists() else set()
    )
    current = date.today().strftime("%Y-%m")
    total = pages = 0
    with (
        append_rows(output, COLUMNS) as (stream, writer),
        months_path.open("a", encoding="utf-8") as done,
    ):
        for tag in tags:
            for year, month in months(start, end):
                key = f"{tag} {year}-{month:02d}"
                if key in finished:
                    continue
                new = 0
                for items in client.entries(tag, year, month):
                    for entry in items:
                        day = (entry.get("created_at") or "")[:10]
                        if str(entry["id"]) in saved or not str(start) <= day <= str(end):
                            continue
                        writer.writerow(rows.entry(entry, tag))
                        saved.add(str(entry["id"]))
                        new += 1
                    stream.flush()
                    pages += 1
                    if page_limit and pages >= page_limit:
                        log(f"Page limit reached; {total + new} new entries.")
                        return total + new
                if f"{year}-{month:02d}" < current:
                    done.write(key + "\n")
                    done.flush()
                total += new
                log(f"#{tag} {year}-{month:02d}: {new} new entries, {total} in total")
    return total


def collect_comments(
    client: WykopClient,
    rows: RowBuilder,
    output: Path,
    tags: Iterable[str],
    start: date,
    end: date,
    min_upvotes: int | None = None,
    first: int = 5,
    limit: int | None = None,
    log: Callable[[str], None] = print,
) -> int:
    """Append selected comments of saved entries that have comments but none saved yet.

    Tags are matched against all tags of an entry, not only the one that found it.
    """
    saved = read_rows(output, COLUMNS)
    empty_path = side_file(output, "no_comments")
    done = {row["parent_id"] for row in saved if row["type"] == COMMENT}
    if empty_path.exists():
        done |= set(empty_path.read_text(encoding="utf-8").split())
    wanted = set(tags)
    todo = [
        row
        for row in saved
        if row["type"] == ENTRY
        and row["entry_id"] not in done
        and int(row["comment_count"] or 0) > 0
        and wanted & set(row["tags"].split(","))
        and str(start) <= row["created_at"][:10] <= str(end)
    ][:limit]
    log(f"Entries to complete with comments: {len(todo)}")
    total, started = 0, time.time()
    with (
        append_rows(output, COLUMNS) as (stream, writer),
        empty_path.open("a", encoding="utf-8") as empty,
    ):
        for n, row in enumerate(todo, 1):
            chosen = select_comments(client.comments(int(row["entry_id"])), min_upvotes, first)
            writer.writerows(
                rows.comment(c, row["entry_id"], row["url"], row["tag"]) for c in chosen
            )
            stream.flush()
            if not chosen:
                empty.write(row["entry_id"] + "\n")
                empty.flush()
            total += len(chosen)
            if n % 50 == 0:
                hours = (time.time() - started) / n * (len(todo) - n) / 3600
                log(f"{n}/{len(todo)} entries, {total} comments, ~{hours:.1f} h left")
    log(f"Saved {total} comments.")
    return total
