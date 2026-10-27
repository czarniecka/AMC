"""Validate saved strong-model JSON answers and import them into review SQLite."""

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

AI = {"yes", "no"}
STANCE = {"threat", "reassurance", "opportunity", "mixed", "none"}
ATTITUDE = {"positive", "negative", "mixed", "neutral"}
THREAT = {"job_loss", "hiring", "pay", "skills", "other"}
COMPETENCE = {"more", "fewer", "unchanged", "none"}
SECTOR = {"it", "creative", "office", "service", "education", "other", "unspecified"}
FIELDS = {
    "id",
    "ai",
    "work",
    "stance",
    "job_insecurity",
    "attitude",
    "threat_type",
    "competence_claim",
    "sector",
}


def validate_answer(answer: object, expected_batch: str, expected_ids: list[str]) -> list[dict]:
    if not isinstance(answer, dict) or set(answer) != {"batch_id", "labels"}:
        raise ValueError("Expected only batch_id and labels")
    labels = answer["labels"]
    if answer["batch_id"] != expected_batch or not isinstance(labels, list):
        raise ValueError("Wrong batch_id or labels type")
    if len(labels) != len(expected_ids):
        raise ValueError("Missing or extra comment labels")
    for item, expected_id in zip(labels, expected_ids, strict=True):
        if not isinstance(item, dict) or set(item) != FIELDS or item["id"] != expected_id:
            raise ValueError(f"Wrong fields, order or ID near {expected_id}")
        ai, work, stance = item["ai"], item["work"], item["stance"]
        if ai not in AI or work not in AI or stance not in STANCE:
            raise ValueError(f"Invalid stage-1 label for {expected_id}")
        if (ai == "no" or work == "no") and stance != "none":
            raise ValueError(f"Non-work/AI comment has a stance: {expected_id}")
        if work == "yes":
            if item["job_insecurity"] not in AI:
                raise ValueError(f"Missing job_insecurity for {expected_id}")
        elif item["job_insecurity"] is not None:
            raise ValueError(f"Non-work comment has job_insecurity: {expected_id}")
        if ai == "yes" and work == "yes":
            if (
                item["attitude"] not in ATTITUDE
                or item["competence_claim"] not in COMPETENCE
                or item["sector"] not in SECTOR
            ):
                raise ValueError(f"Invalid stage-2 label for {expected_id}")
            if stance in {"threat", "mixed"}:
                if item["threat_type"] not in THREAT:
                    raise ValueError(f"Missing threat_type for {expected_id}")
            elif item["threat_type"] is not None:
                raise ValueError(f"Unexpected threat_type for {expected_id}")
        elif any(
            item[field] is not None
            for field in ("attitude", "threat_type", "competence_claim", "sector")
        ):
            raise ValueError(f"Stage-2 labels on non-AI/work comment: {expected_id}")
    return labels


def import_answers(review_dir: Path, model: str) -> dict:
    if not model.strip():
        raise ValueError("Provide the exact strong-model name")
    manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
    response_files = sorted((review_dir / "responses").glob("review_*.json"))
    staged = []
    for path in response_files:
        prompt_path = review_dir / "prompts" / f"{path.stem}.md"
        prompt = prompt_path.read_text(encoding="utf-8")
        guide, payload_text = prompt.rsplit("\nDANE DO OCENY:\n", 1)
        if hashlib.sha256(guide.encode()).hexdigest() != manifest["instruction_sha256"]:
            raise ValueError(f"Instruction changed in {prompt_path}")
        payload = json.loads(payload_text)
        expected_ids = [item["id"] for item in payload["comments"]]
        labels = validate_answer(
            json.loads(path.read_text(encoding="utf-8")), payload["batch_id"], expected_ids
        )
        staged.append((path, labels))
    inserted = 0
    with sqlite3.connect(review_dir / "annotations.sqlite3") as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for path, labels in staged:
            for item in labels:
                item_id = item["id"]
                review = connection.execute(
                    "SELECT review_batch_id FROM review_sample WHERE item_id=?", (item_id,)
                ).fetchone()
                if review is None or review[0] != path.stem:
                    raise ValueError(f"Response ID is outside its review batch: {item_id}")
                old = connection.execute(
                    "SELECT ai,work,stance,job_insecurity,model,instruction_hash,response_file "
                    "FROM stage1_strong WHERE item_id=?",
                    (item_id,),
                ).fetchone()
                if old:
                    expected = (
                        item["ai"],
                        item["work"],
                        item["stance"],
                        item["job_insecurity"],
                        model,
                        manifest["instruction_sha256"],
                        path.name,
                    )
                    if old != expected:
                        raise ValueError(f"Strong label changed after import: {item_id}")
                    old_stage2 = connection.execute(
                        "SELECT attitude,threat_type,competence_claim,sector "
                        "FROM stage2_strong WHERE item_id=?",
                        (item_id,),
                    ).fetchone()
                    expected_stage2 = (
                        (
                            item["attitude"],
                            item["threat_type"],
                            item["competence_claim"],
                            item["sector"],
                        )
                        if item["ai"] == "yes" and item["work"] == "yes"
                        else None
                    )
                    if old_stage2 != expected_stage2:
                        raise ValueError(f"Stage-2 label changed after import: {item_id}")
                    continue
                connection.execute(
                    "INSERT INTO stage1_strong VALUES (?,?,?,?,?,?,?,?)",
                    (
                        item_id,
                        item["ai"],
                        item["work"],
                        item["stance"],
                        item["job_insecurity"],
                        model,
                        manifest["instruction_sha256"],
                        path.name,
                    ),
                )
                if item["ai"] == "yes" and item["work"] == "yes":
                    connection.execute(
                        "INSERT INTO stage2_strong VALUES (?,?,?,?,?)",
                        (
                            item_id,
                            item["attitude"],
                            item["threat_type"],
                            item["competence_claim"],
                            item["sector"],
                        ),
                    )
                inserted += 1
        total = connection.execute("SELECT COUNT(*) FROM stage1_strong").fetchone()[0]
    return {
        "response_files": len(response_files),
        "new_labels": inserted,
        "strong_labeled": total,
        "review_target": manifest["review_count"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--model", required=True)
    args = parser.parse_args()
    try:
        result = import_answers(args.review_dir, args.model)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(2, f"Import stopped: {error}\n")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
