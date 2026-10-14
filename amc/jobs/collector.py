"""Build the sample manifest, then fetch and parse pending advertisements."""

from collections.abc import Callable, Sequence

from amc.jobs.client import KPRMClient
from amc.jobs.parser import ParseError, parse_ad
from amc.jobs.sampling import Window, draw, id_range
from amc.jobs.storage import JobStore, SampleItem

SAVE_EVERY = 20


def build_sample(
    store: JobStore,
    client: KPRMClient,
    windows: Sequence[Window],
    per_window: int,
    seed: int,
    log: Callable[[str], None] = print,
) -> None:
    """Add manifest rows for windows that have none; existing rows are never redrawn."""
    known = {item.window for item in store.sample}
    for window in windows:
        if window.name in known:
            continue
        ids = id_range(client, window)
        log(f"{window.name}: IDs {ids.start}-{ids.stop - 1}")
        store.sample.extend(SampleItem(ad_id, window.name) for ad_id in draw(ids, per_window, seed))
        store.save()


def collect(
    store: JobStore,
    client: KPRMClient,
    limit: int | None = None,
    log: Callable[[str], None] = print,
) -> None:
    """Fetch pending items, resuming after interruption; progress is saved periodically."""
    pending = [item for item in store.sample if item.status == "pending"][:limit]
    done = 0
    try:
        for item in pending:
            html = client.fetch_ad(item.ad_id)
            try:
                if html is None:
                    raise ParseError("missing")
                ad, text = parse_ad(html)
            except ParseError:
                item.status = "missing"
            else:
                store.ads[ad.ad_id], store.texts[ad.ad_id] = ad, text
                item.status = "ok"
            done += 1
            if done % SAVE_EVERY == 0:
                store.save()
                log(f"{done}/{len(pending)} processed")
    finally:
        store.save()
    log(f"Processed {done} advertisements ({client.request_count} requests).")
