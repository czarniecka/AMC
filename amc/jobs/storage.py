"""CSV persistence for the sample manifest and parsed advertisements."""

import csv
import os
from dataclasses import dataclass
from pathlib import Path

from amc.jobs.models import JobAd, JobAdText
from amc.youtube.api_client import CollectionError
from amc.youtube.exporter import write_csv

SAMPLE_COLUMNS = ("ad_id", "window", "status")
AD_COLUMNS = tuple(JobAd.__dataclass_fields__)
TEXT_COLUMNS = tuple(JobAdText.__dataclass_fields__)
FREE_TEXT = {"title", "institution", "unit", "city", "salary_text", *TEXT_COLUMNS[1:]}
STATUSES = ("pending", "ok", "missing")


@dataclass(slots=True)
class SampleItem:
    ad_id: int
    window: str
    status: str = "pending"


def _decode(value: str) -> str:
    # Reverse the spreadsheet-safety prefix added by write_csv.
    if value.startswith("'") and value[1:].lstrip().startswith(("=", "+", "-", "@")):
        return value[1:]
    return value


def _read(path: Path, columns: tuple[str, ...]) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != columns:
            raise ValueError(f"Unexpected headers in {path.name}")
        return [{key: _decode(value) for key, value in row.items()} for row in reader]


class JobStore:
    """Manifest and parsed ads; one writer per directory enforced by a lock file."""

    def __init__(self, output_dir: Path) -> None:
        output_dir.mkdir(parents=True, exist_ok=True)
        self.dir = output_dir
        self.lock = output_dir / ".jobs.lock"
        try:
            os.close(os.open(self.lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            raise CollectionError(
                "Another job collection is active. "
                "Remove .jobs.lock only after confirming it stopped."
            ) from None
        try:
            self.sample = [
                SampleItem(int(r["ad_id"]), r["window"], r["status"])
                for r in _read(output_dir / "kprm_sample.csv", SAMPLE_COLUMNS)
            ]
            self.ads = {
                int(r["ad_id"]): JobAd(**{**r, "ad_id": int(r["ad_id"])})
                for r in _read(output_dir / "kprm_ads.csv", AD_COLUMNS)
            }
            self.texts = {
                int(r["ad_id"]): JobAdText(**{**r, "ad_id": int(r["ad_id"])})
                for r in _read(output_dir / "kprm_ad_texts.csv", TEXT_COLUMNS)
            }
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        self.lock.unlink(missing_ok=True)

    def save(self) -> None:
        write_csv(self.dir / "kprm_sample.csv", SAMPLE_COLUMNS, self.sample)
        write_csv(self.dir / "kprm_ads.csv", AD_COLUMNS, self.ads.values(), FREE_TEXT)
        write_csv(self.dir / "kprm_ad_texts.csv", TEXT_COLUMNS, self.texts.values(), FREE_TEXT)
