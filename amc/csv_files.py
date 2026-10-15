"""Append-only CSV files for collections too large to rewrite atomically after each record.

New files start with a UTF-8 BOM and a header, like the atomic exports in
`amc.youtube.exporter`. Each row is flushed by the caller, so an interrupted run keeps
everything written so far.
"""

import csv
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def read_rows(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    """All rows, or an empty list when the file does not exist yet."""
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != columns:
            raise ValueError(f"Unexpected headers in {path.name}")
        return list(reader)


@contextmanager
def append_rows(path: Path, columns: tuple[str, ...]) -> Iterator[tuple]:
    """Yield the open stream and a DictWriter; the header is written for a new file."""
    new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8-sig" if new_file else "utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        if new_file:
            writer.writeheader()
            stream.flush()
        yield stream, writer
