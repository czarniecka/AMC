"""Draw a seeded sample of labeled Wykop texts: half with ai and work "yes", half without.

The sample is saved as an Excel workbook, so columns open correctly whatever the regional
list separator is. Requires `openpyxl`. `--exclude` leaves out texts that were already
annotated. With `--blank` the annotators' sheet has empty ai and work columns, and the
model labels, which define the two halves, go to a separate `<output>_key.csv`.
"""

import argparse
import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from openpyxl import Workbook  # noqa: E402
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE  # noqa: E402
from openpyxl.styles import Alignment, Font  # noqa: E402

from amc.csv_files import read_rows  # noqa: E402
from amc.wykop.classification import LABELED_COLUMNS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
WIDTHS = {"created_at": 20, "url": 30, "text": 80}


def write_xlsx(path: Path, rows: list[dict[str, str]]) -> None:
    book = Workbook()
    sheet = book.active
    sheet.title = "sample"
    sheet.append(LABELED_COLUMNS)
    for row in rows:
        # Control characters are invalid in XLSX; every value stays text, so a post that
        # starts with "=" is not read as a formula and IDs are not shown as numbers.
        sheet.append([ILLEGAL_CHARACTERS_RE.sub("", row[column]) for column in LABELED_COLUMNS])
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for line in sheet.iter_rows(min_row=2):
        for cell in line:
            cell.data_type = "s"
            cell.alignment = Alignment(wrap_text=True, vertical="top")
    for cell in sheet[1]:
        sheet.column_dimensions[cell.column_letter].width = WIDTHS.get(cell.value, 12)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions
    book.save(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/wykop/wykop_labeled.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/wykop/wykop_sample.xlsx")
    parser.add_argument("--count", type=int, default=150, help="total texts (split evenly)")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument(
        "--exclude",
        type=Path,
        action="append",
        default=[],
        help="CSV with type and entry_id columns of texts to leave out (repeatable)",
    )
    parser.add_argument(
        "--blank", action="store_true", help="empty ai and work for blind annotation"
    )
    options = parser.parse_args(argv)
    key = options.output.with_name(options.output.stem + "_key.csv")
    for path in (options.output, key) if options.blank else (options.output,):
        if path.exists():
            print(f"{path} already exists; it may hold labels, so it is not overwritten.")
            return 1
    csv.field_size_limit(2**31 - 1)
    excluded = set()
    for path in options.exclude:
        with path.open(encoding="utf-8-sig", newline="") as stream:
            excluded |= {(row["type"], row["entry_id"]) for row in csv.DictReader(stream)}
    rows = [
        row
        for row in read_rows(options.input, LABELED_COLUMNS)
        if (row["type"], row["entry_id"]) not in excluded
    ]
    both = [row for row in rows if row["ai"] == "yes" and row["work"] == "yes"]
    rest = [row for row in rows if not (row["ai"] == "yes" and row["work"] == "yes")]
    half = options.count // 2
    if len(both) < half or len(rest) < options.count - half:
        print(f"Not enough texts: {len(both)} with ai and work, {len(rest)} without.")
        return 1
    rng = random.Random(options.seed)
    chosen = rng.sample(both, half) + rng.sample(rest, options.count - half)
    rng.shuffle(chosen)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    if options.blank:
        with key.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=("type", "entry_id", "ai", "work"))
            writer.writeheader()
            writer.writerows({name: row[name] for name in writer.fieldnames} for row in chosen)
        chosen = [{**row, "ai": "", "work": ""} for row in chosen]
    write_xlsx(options.output, chosen)
    print(
        f"Wrote {len(chosen)} texts to {options.output}: {half} of {len(both)} with ai and "
        f"work, {options.count - half} of {len(rest)} without; {len(excluded)} excluded."
    )
    if options.blank:
        print(f"Model labels for the sample are in {key}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
