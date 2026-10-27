"""Export an existing strong-review sample as portable JSON batches for Git."""

import argparse
import hashlib
import json
from pathlib import Path


def export(review_dir: Path, output_dir: Path) -> dict:
    if output_dir.exists():
        raise ValueError(f"Output already exists: {output_dir}")
    manifest = json.loads((review_dir / "manifest.json").read_text(encoding="utf-8"))
    prompt_paths = sorted((review_dir / "prompts").glob("review_*.md"))
    if len(prompt_paths) != manifest["review_batches"]:
        raise ValueError("Prompt count differs from review manifest")
    instruction_text = None
    payloads = []
    seen = set()
    for path in prompt_paths:
        guide, payload_text = path.read_text(encoding="utf-8").rsplit("\nDANE DO OCENY:\n", 1)
        if hashlib.sha256(guide.encode()).hexdigest() != manifest["instruction_sha256"]:
            raise ValueError(f"Instruction hash mismatch: {path}")
        if instruction_text is None:
            instruction_text = guide
        elif guide != instruction_text:
            raise ValueError(f"Inconsistent instruction: {path}")
        payload = json.loads(payload_text)
        if payload["batch_id"] != path.stem or set(payload) != {"batch_id", "comments"}:
            raise ValueError(f"Invalid batch: {path}")
        for comment in payload["comments"]:
            if set(comment) != {"id", "text"} or comment["id"] in seen:
                raise ValueError(f"Duplicate or invalid comment in {path}")
            seen.add(comment["id"])
        payloads.append(payload)
    if len(seen) != manifest["review_count"]:
        raise ValueError("Comment count differs from review manifest")
    output_dir.mkdir(parents=True)
    (output_dir / "batches").mkdir()
    (output_dir / "responses").mkdir()
    (output_dir / "responses" / ".gitkeep").write_text("", encoding="utf-8")
    (output_dir / "instructions.md").write_text(instruction_text, encoding="utf-8")
    for payload in payloads:
        (output_dir / "batches" / f"{payload['batch_id']}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    public_manifest = {
        key: manifest[key]
        for key in (
            "source_sha256",
            "instruction_sha256",
            "seed",
            "target",
            "batch_size",
            "source_comments",
            "luna_labeled",
            "missing_luna_labels",
            "review_count",
            "review_batches",
            "review_by_bucket_period",
        )
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(public_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"batches": len(payloads), "comments": len(seen)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = export(args.review_dir, args.output)
    except (OSError, KeyError, ValueError) as error:
        parser.exit(2, f"Export stopped: {error}\n")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
