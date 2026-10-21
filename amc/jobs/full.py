"""Collect every advertisement in an ID range into an appendable RepOD-format CSV.

Unlike the pilot sample, the full collection is too large for atomic rewrites, so rows are
appended and flushed one by one. IDs without an advertisement are listed in
`<name>_missing.txt` and are not requested again.
"""

import time
from collections.abc import Callable, Iterable
from pathlib import Path
from urllib import robotparser

from amc.csv_files import append_rows, read_rows
from amc.jobs.client import BASE_URL, KPRMClient, user_agent
from amc.jobs.repod import COLUMNS, parse_repod
from amc.youtube.api_client import CollectionError

KEY_FIELDS = ("ad_institution", "ad_date_announced", "ad_requirements1")
REPORT_EVERY = 25


def missing_path(output: Path) -> Path:
    return output.with_name(output.stem + "_missing.txt")


def known_ids(output: Path) -> set[int]:
    """IDs already saved or known to be missing."""
    ids = {int(row["ad_id"]) for row in read_rows(output, COLUMNS) if row["ad_id"]}
    missing = missing_path(output)
    if missing.exists():
        ids |= {int(x) for x in missing.read_text(encoding="utf-8").split()}
    return ids


def check_robots() -> None:
    robots = robotparser.RobotFileParser(BASE_URL + "/robots.txt")
    robots.read()
    if not robots.can_fetch(user_agent(), BASE_URL + "/a/b/c,1,v8"):
        raise CollectionError("robots.txt disallows advertisement pages; collection stopped.")


def collect_range(
    client: KPRMClient,
    output: Path,
    ids: Iterable[int],
    limit: int | None = None,
    log: Callable[[str], None] = print,
) -> int:
    """Fetch IDs not seen before; returns the number of saved advertisements."""
    skip = known_ids(output)
    todo = [ad_id for ad_id in ids if ad_id not in skip][:limit]
    log(f"IDs to check: {len(todo)} (skipped as known: {len(skip)})")
    saved = incomplete = 0
    start = time.time()
    with (
        append_rows(output, COLUMNS) as (stream, writer),
        missing_path(output).open("a", encoding="utf-8") as missing,
    ):
        for n, ad_id in enumerate(todo, 1):
            try:
                found = client.find_ad(ad_id)
            except CollectionError as error:
                # Not marked missing, so the ID is retried on the next run.
                log(f"  ID {ad_id}: {error}")
                continue
            if found is None:
                missing.write(f"{ad_id}\n")
                missing.flush()
            else:
                row = parse_repod(*found, ad_id)
                writer.writerow(row)
                stream.flush()
                saved += 1
                gaps = [field for field in KEY_FIELDS if not row[field]]
                if gaps:
                    incomplete += 1
                    log(f"  ID {ad_id} lacks {', '.join(gaps)} (template {row['template'] or '?'})")
            if n % REPORT_EVERY == 0:
                hours = (time.time() - start) / n * (len(todo) - n) / 3600
                log(f"{n}/{len(todo)} checked, {saved} saved, last ID {ad_id}, ~{hours:.1f} h left")
    log(f"Saved {saved} advertisements ({incomplete} lack a key field).")
    return saved
