"""Prepare screening batches for the stage 1 classifier (ai, work) and merge its labels."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from amc.youtube.stage1_files import export_input, merge_output  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    export = commands.add_parser("export", help="write stage1_input.csv from batches.jsonl")
    merge = commands.add_parser("merge", help="write stage1_labels.csv from stage1_output.csv")
    for command in (export, merge):
        command.add_argument("--screening-dir", type=Path, required=True)
    merge.add_argument("--model", help="needed only if the output has several models")
    merge.add_argument("--prompt-hash", help="needed only if the output has several prompts")
    options = parser.parse_args(argv)
    try:
        if options.command == "export":
            print(f"Wrote {export_input(options.screening_dir)} comments to stage1_input.csv")
        else:
            counts = merge_output(
                options.screening_dir, model=options.model, prompt_hash=options.prompt_hash
            )
            print(f"Merged into stage1_labels.csv: {counts}")
    except (OSError, ValueError, KeyError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
