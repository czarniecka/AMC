"""Blind human annotation, adjudication and held-out evaluation of YouTube labels."""

import argparse
import csv
import hashlib
import json
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from amc.classification.classifier import IMPACT, RELEVANCE

ROOT = Path(__file__).resolve().parents[2]
CODEBOOK = ROOT / "config/youtube/comment_codebook.json"
LABELING = ROOT / "data/youtube/labeling"
SHEET = ("sample_id", "text_clean", "relevance", "impact", "note")
KEY = ("sample_id", "split", "video_id", "comment_id", "text_hash")


def read(path: Path, columns: tuple[str, ...]) -> list[dict]:
    """Read required fields and reject malformed rows."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        if not set(columns).issubset(reader.fieldnames or ()):
            raise ValueError(f"Invalid columns: {path.name}")
        rows = list(reader)
    if any(None in row or any(value is None for value in row.values()) for row in rows):
        raise ValueError(f"Malformed rows: {path.name}")
    return rows


def write_new(path: Path, columns: tuple[str, ...], rows: list[dict]) -> None:
    """Never overwrite annotation work or prior evaluation reports."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def text_value(text: str) -> str:
    """Decode only the CSV exporter's formula-safety prefix."""
    return (
        text[1:]
        if text.startswith("'") and text[1:].lstrip().startswith(("=", "+", "-", "@"))
        else text
    )


def fingerprint(text: str) -> str:
    return hashlib.sha256(text_value(text).encode()).hexdigest()


def unique(rows: list[dict], field: str) -> dict[str, dict]:
    result = {row[field]: row for row in rows}
    if len(result) != len(rows) or "" in result:
        raise ValueError(f"Duplicate or empty {field}")
    return result


def labels(row: dict) -> None:
    if row["relevance"] not in RELEVANCE or row["impact"] not in IMPACT:
        raise ValueError("Incomplete or invalid human/model labels")
    if row["relevance"] != "relevant" and row["impact"] != "unclear":
        raise ValueError("Unrelated/unclear relevance requires unclear impact")


def prepare(source: Path, output: Path, pilot: int, evaluation: int, seed: int) -> None:
    """Separate videos and identical texts across development and evaluation splits."""
    if output.exists():
        raise ValueError("Labeling directory already exists; choose a new output directory")
    if pilot < 1 or evaluation < 1:
        raise ValueError("Sample sizes must be positive")
    rows = read(source, ("video_id", "comment_id", "text_clean"))
    identities = [(row["video_id"], row["comment_id"]) for row in rows]
    if len(set(identities)) != len(rows):
        raise ValueError("Source has duplicate comment identifiers")
    rng = random.Random(seed)
    rng.shuffle(rows)
    groups: dict[str, list] = {}
    seen_text = set()
    for row in rows:
        digest = fingerprint(row["text_clean"])
        if not text_value(row["text_clean"]).strip() or digest in seen_text:
            continue
        seen_text.add(digest)
        groups.setdefault(row["video_id"], []).append(row)
    videos = list(groups)
    rng.shuffle(videos)
    # Search a reproducible video partition with enough comments for both samples.
    partition = None
    for _ in range(1000):
        rng.shuffle(videos)
        pilot_ids = set(videos[: max(1, len(videos) // 4)])
        dev = [row for video in videos if video in pilot_ids for row in groups[video]]
        test = [row for video in videos if video not in pilot_ids for row in groups[video]]
        if len(dev) >= pilot and len(test) >= evaluation:
            partition = (dev, test)
            break
    if partition is None:
        raise ValueError("Insufficient distinct videos/texts for video-disjoint requested samples")
    codebook = json.loads(CODEBOOK.read_text(encoding="utf-8"))
    keys = []
    output.mkdir(parents=True)
    for split, pool, count in zip(
        ("pilot", "evaluation"), partition, (pilot, evaluation), strict=True
    ):
        selected = rng.sample(pool, count)
        sheet = []
        for number, row in enumerate(selected, 1):
            sample_id = f"{split[0].upper()}{number:03d}"
            sheet.append(dict(zip(SHEET, (sample_id, row["text_clean"], "", "", ""), strict=True)))
            keys.append(
                dict(
                    zip(
                        KEY,
                        (
                            sample_id,
                            split,
                            row["video_id"],
                            row["comment_id"],
                            fingerprint(row["text_clean"]),
                        ),
                        strict=True,
                    )
                )
            )
        for annotator in ("a", "b"):
            write_new(output / f"{split}_annotator_{annotator}.csv", SHEET, sheet)
    write_new(output / "sample_key.csv", KEY, keys)
    manifest = {
        "seed": seed,
        "pilot_size": pilot,
        "evaluation_size": evaluation,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "codebook_version": codebook["version"],
        "codebook_sha256": hashlib.sha256(CODEBOOK.read_bytes()).hexdigest(),
        "split_policy": "video-disjoint, exact-text-deduplicated; no model labels used",
        "limitations": (
            "Not language-stratified; verify language coverage manually. "
            "Not population-representative."
        ),
        "key_sha256": hashlib.sha256((output / "sample_key.csv").read_bytes()).hexdigest(),
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (output / "codebook.json").write_bytes(CODEBOOK.read_bytes())


def adjudicate(a: Path, b: Path, output: Path) -> dict:
    """Retain original ratings; leave disputed final labels blank for human resolution."""
    left = unique(read(a, SHEET), "sample_id")
    right = unique(read(b, SHEET), "sample_id")
    if not left or left.keys() != right.keys():
        raise ValueError("Annotators must label exactly the same non-empty sample")
    result = []
    agreement = Counter()
    for key, first in left.items():
        second = right[key]
        labels(first)
        labels(second)
        if first["text_clean"] != second["text_clean"]:
            raise ValueError("Annotators changed comment text")
        same = all(first[field] == second[field] for field in ("relevance", "impact"))
        for field in ("relevance", "impact"):
            agreement[field] += first[field] == second[field]
        result.append(
            {
                "sample_id": key,
                "text_clean": first["text_clean"],
                "relevance_a": first["relevance"],
                "impact_a": first["impact"],
                "relevance_b": second["relevance"],
                "impact_b": second["impact"],
                "note_a": first["note"],
                "note_b": second["note"],
                "relevance": first["relevance"] if same else "",
                "impact": first["impact"] if same else "",
                "reviewer": "",
                "reviewed_at": "",
                "resolution_note": "",
            }
        )
    write_new(output, tuple(result[0]), result)
    return {field: agreement[field] / len(left) for field in ("relevance", "impact")}


def single_annotator(sheet: Path, output: Path, annotator: str, key_path: Path, split: str) -> None:
    """Promote complete human labels without fabricating an independent second rating."""
    if not annotator.strip():
        raise ValueError("An annotator identifier is required")
    rows = read(sheet, SHEET)
    indexed = unique(rows, "sample_id")
    keys = unique(read(key_path, KEY), "sample_id")
    expected = {key for key, row in keys.items() if row["split"] == split}
    if not rows or indexed.keys() != expected:
        raise ValueError("Sheet must cover exactly the selected split")
    final = []
    for row in rows:
        labels(row)
        if fingerprint(row["text_clean"]) != keys[row["sample_id"]]["text_hash"]:
            raise ValueError("Annotated text differs from the frozen sample")
        final.append(
            {
                **row,
                "reviewer": annotator.strip(),
                "reviewed_at": datetime.now(timezone.utc).isoformat(),
                "annotation_method": "single_annotator",
                "resolution_note": (
                    "Imported from one human annotation sheet; no independent adjudication."
                ),
            }
        )
    write_new(output, tuple(final[0]), final)


def metrics(gold: list[str], predicted: list[str], classes: tuple[str, ...]) -> dict:
    matrix = {actual: {guess: 0 for guess in classes} for actual in classes}
    for actual, guess in zip(gold, predicted, strict=True):
        matrix[actual][guess] += 1
    per_class = {}
    for name in classes:
        tp = matrix[name][name]
        support = sum(matrix[name].values())
        guessed = sum(matrix[actual][name] for actual in classes)
        fp, fn = guessed - tp, support - tp
        per_class[name] = {
            "support": support,
            "precision": tp / guessed if guessed else None,
            "recall": tp / support if support else None,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
        }
    f1s = [value["f1"] for value in per_class.values() if value["f1"] is not None]
    return {
        "n": len(gold),
        "accuracy": sum(a == b for a, b in zip(gold, predicted, strict=True)) / len(gold)
        if gold
        else None,
        "macro_f1": sum(f1s) / len(f1s) if f1s else None,
        "macro_policy": (
            "Mean over classes present in gold or predictions; absent classes have null metrics"
        ),
        "per_class": per_class,
        "confusion_matrix": matrix,
    }


def evaluate(
    gold_path: Path, key_path: Path, predictions: Path, model: str, prompt_hash: str, split: str
) -> dict:
    """Require full, unambiguous, text-matched coverage for one prediction cohort."""
    gold = unique(
        read(
            gold_path, ("sample_id", "text_clean", "relevance", "impact", "reviewer", "reviewed_at")
        ),
        "sample_id",
    )
    keys = unique(read(key_path, KEY), "sample_id")
    manifest_path = key_path.parent / "manifest.json"
    manifest = None
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest["key_sha256"] != hashlib.sha256(key_path.read_bytes()).hexdigest():
            raise ValueError("Sample key differs from the frozen manifest")
        frozen_codebook = key_path.parent / "codebook.json"
        if hashlib.sha256(frozen_codebook.read_bytes()).hexdigest() != manifest["codebook_sha256"]:
            raise ValueError("Frozen codebook differs from the manifest")
    expected = {key for key, row in keys.items() if row["split"] == split}
    if not gold or gold.keys() != expected:
        raise ValueError("Gold must contain exactly the selected split")
    predictions_by_id = {}
    for row in read(
        predictions,
        ("video_id", "comment_id", "text_hash", "model", "prompt_hash", "relevance", "impact"),
    ):
        if row["model"] != model or row["prompt_hash"] != prompt_hash:
            continue
        identity = (row["video_id"], row["comment_id"], row["text_hash"])
        if identity in predictions_by_id:
            raise ValueError("Duplicate predictions in selected cohort")
        labels(row)
        predictions_by_id[identity] = row
    paired = []
    for sample_id, row in gold.items():
        labels(row)
        if not row["reviewer"].strip() or not row["reviewed_at"].strip():
            raise ValueError("Gold requires reviewer and reviewed_at for every row")
        key = keys[sample_id]
        if fingerprint(row["text_clean"]) != key["text_hash"]:
            raise ValueError("Gold text differs from frozen sample")
        identity = (key["video_id"], key["comment_id"], key["text_hash"])
        if identity not in predictions_by_id:
            raise ValueError("Missing predictions for selected gold sample; evaluation aborted")
        paired.append((row, predictions_by_id[identity]))
    report = {
        field: metrics([a[field] for a, b in paired], [b[field] for a, b in paired], classes)
        for field, classes in (("relevance", RELEVANCE), ("impact", IMPACT))
    }
    relevant = [(a, b) for a, b in paired if a["relevance"] == "relevant"]
    report["impact_on_gold_relevant"] = metrics(
        [a["impact"] for a, b in relevant], [b["impact"] for a, b in relevant], IMPACT
    )
    report.update(
        {
            "split": split,
            "model": model,
            "prompt_hash": prompt_hash,
            "gold_sha256": hashlib.sha256(gold_path.read_bytes()).hexdigest(),
            "predictions_sha256": hashlib.sha256(predictions.read_bytes()).hexdigest(),
            "key_sha256": hashlib.sha256(key_path.read_bytes()).hexdigest(),
        }
    )
    report["sampling_manifest"] = manifest
    report["coverage"] = {"expected": len(gold), "matched": len(paired)}
    report["annotation_methods"] = sorted(
        {row.get("annotation_method", "not_recorded") for row in gold.values()}
    )
    report["annotation_limitations"] = (
        "Single-annotator reference; inter-annotator agreement was not measured."
        if "single_annotator" in report["annotation_methods"]
        else None
    )
    report["model_informed_review_count"] = sum(
        "[model-informed pilot review]" in row.get("note", "") for row in gold.values()
    )
    report["independent_evaluation"] = (
        split == "evaluation" and report["model_informed_review_count"] == 0
    )
    report["disagreements"] = [
        {
            "sample_id": actual["sample_id"],
            "human_relevance": actual["relevance"],
            "model_relevance": prediction["relevance"],
            "human_impact": actual["impact"],
            "model_impact": prediction["impact"],
        }
        for actual, prediction in paired
        if any(actual[field] != prediction[field] for field in ("relevance", "impact"))
    ]
    return report


def save_report(report: dict, output: Path) -> None:
    """Publish JSON and job-codebook-style CSV metrics without replacing prior reports."""
    paths = [output] + [
        output.with_suffix(suffix)
        for suffix in (".metrics.csv", ".confusion.csv", ".disagreements.csv")
    ]
    if any(path.exists() for path in paths):
        raise ValueError("Report outputs already exist; choose a new report name")
    scores, confusion = [], []
    for field in ("relevance", "impact", "impact_on_gold_relevant"):
        result = report[field]
        for category, values in result["per_class"].items():
            matrix = result["confusion_matrix"]
            tp = matrix[category][category]
            fp = sum(matrix[actual][category] for actual in matrix) - tp
            fn = sum(matrix[category].values()) - tp
            scores.append(
                {
                    "applied_to": field,
                    "category": category,
                    "gold": values["support"],
                    "tp": tp,
                    "fp": fp,
                    "fn": fn,
                    "precision": values["precision"],
                    "recall": values["recall"],
                    "f1": values["f1"],
                }
            )
        for actual, counts in result["confusion_matrix"].items():
            for predicted, count in counts.items():
                confusion.append(
                    {"applied_to": field, "human": actual, "model": predicted, "count": count}
                )
    write_new(
        paths[1],
        ("applied_to", "category", "gold", "tp", "fp", "fn", "precision", "recall", "f1"),
        scores,
    )
    write_new(paths[2], ("applied_to", "human", "model", "count"), confusion)
    write_new(
        paths[3],
        ("sample_id", "human_relevance", "model_relevance", "human_impact", "model_impact"),
        report["disagreements"],
    )
    with output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, indent=2, allow_nan=False)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser("prepare")
    prep.add_argument(
        "--input", type=Path, default=ROOT / "data/youtube/yt_comments_anonymized.csv"
    )
    prep.add_argument("--output", type=Path, default=LABELING)
    prep.add_argument("--pilot", type=int, default=50)
    prep.add_argument("--evaluation", type=int, default=200)
    prep.add_argument("--seed", type=int, default=20261015)
    adj = sub.add_parser("adjudicate")
    adj.add_argument("--a", type=Path, required=True)
    adj.add_argument("--b", type=Path, required=True)
    adj.add_argument("--output", type=Path, required=True)
    single = sub.add_parser("single-gold")
    single.add_argument("--sheet", type=Path, required=True)
    single.add_argument("--output", type=Path, required=True)
    single.add_argument("--annotator", required=True)
    single.add_argument("--key", type=Path, default=LABELING / "sample_key.csv")
    single.add_argument("--split", choices=("pilot", "evaluation"), default="pilot")
    val = sub.add_parser("evaluate")
    val.add_argument("--gold", type=Path, required=True)
    val.add_argument("--key", type=Path, default=LABELING / "sample_key.csv")
    val.add_argument(
        "--predictions", type=Path, default=ROOT / "data/youtube/yt_comments_classified.csv"
    )
    val.add_argument("--model", required=True)
    val.add_argument("--prompt-hash", required=True)
    val.add_argument("--split", choices=("pilot", "evaluation"), default="evaluation")
    val.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.input, args.output, args.pilot, args.evaluation, args.seed)
            print("Created blind sheets, frozen codebook, manifest and private sample key.")
        elif args.command == "adjudicate":
            print(json.dumps(adjudicate(args.a, args.b, args.output), indent=2))
        elif args.command == "single-gold":
            single_annotator(args.sheet, args.output, args.annotator, args.key, args.split)
            print("Saved single-annotator reference. No second annotator or agreement is implied.")
        else:
            report = evaluate(
                args.gold, args.key, args.predictions, args.model, args.prompt_hash, args.split
            )
            save_report(report, args.output)
            print(
                "JSON report and CSV metrics/confusion/disagreements saved. "
                "Source labels unchanged."
            )
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        parser.exit(1, f"Validation stopped: {error}\n")
