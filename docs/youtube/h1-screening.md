# H1 comment screening batches

H1 asks whether the share of online comments expressing concern about job security
in the face of AI grows after the November 2022 ChatGPT release. The unit is a
comment, not a video. The preparation script does not call a model; the separate
runner below does. H2 concerns job advertisements and is handled separately.

Use the pre/post work-topic sample on this branch for the H1 comparison:

```text
uv run --locked python scripts/youtube/prepare_screening.py --database data/youtube/work_sample_v2/sample.sqlite3 --output data/youtube/screening/work_v1
```

The older reviewed-video pilot can still be prepared from its CSV by omitting
`--database` and choosing another output directory. Keep these two collection
frames separate; their comments can overlap and their selection rules differ.
The existing `work_sample_v2` database remains usable for screening. A new
collection with the branch's updated query list and minimum-comment rule requires
a new database path, such as `data/youtube/work_sample_v3/sample.sqlite3`.

The output directory must be new. `batches.jsonl` contains one JSON object per
line, with up to 100 comments, each carrying a short `id` and its text. Batches
also stop before `--max-batch-chars` (default 30000) to avoid oversized requests.
The script shuffles comments reproducibly (`--seed 42`). It keeps repeated text
from different comments because H1 concerns the share of actual comments.

`screening_config.json` contains the exact screening instruction, an example
response, source file hash and counts. The runner sends the instruction and one
line of `batches.jsonl` per request. It requires one JSON response containing
`batch_id` and `labels` with one entry per input `id`. Each label has
`h1_related` and `job_security_concern`, both `yes`, `no`, or `unclear`.
Malformed or incomplete responses stop the run; rerun after checking the error.
Completed batches are skipped.

## Run GPT-6 Luna

Set `OPENAI_API_KEY` in your private `.env` or environment. Sending comments to
this API transfers their text to an external provider and incurs API charges.
Start with one batch and inspect the output:

```text
uv run --locked python scripts/youtube/run_screening.py --input-dir data/youtube/screening/work_v1 --output data/youtube/screening/work_v1/luna_predictions.jsonl --limit-batches 1
```

Rerun the same command without `--limit-batches 1` to process the remaining
batches. Use the same output path, input snapshot and model to resume. The output
is append-only JSONL with validated labels, model name, instruction hash and
source hash. A changed model, prompt or input needs a different output file.
The runner uses the Responses API synchronously, one request per prepared batch;
the project's JSONL is not itself an OpenAI Batch API request file.

`manifest.csv` maps IDs back to source `video_id`, `comment_id`, publication time,
pre/post period and text hash. The model input contains only comment text and a
short ID, so it cannot use video titles or publication dates to guess labels.
The release boundary is 2022-11-30 00:00 UTC. The reviewed-video CSV pilot begins
in 2023 and cannot provide a pre-release comparison by itself. The work-topic
SQLite sample on this branch contains both periods and determines period from
comment publication date, including post-launch comments under older videos.
Its collection frame, English filters and limitations are documented in
[English YouTube comment sample](random-sample.md).

Screening output is a selection aid for a 5–10k larger-model review set, not a
gold standard or a prevalence estimate. Keep a random component in that review
set alongside clear positive, clear negative and uncertain comments. For final
H1 prevalence estimates, use sampling weights or a separate probability sample;
the enriched review set deliberately changes the class proportions. Validate
the final classifier against human-reviewed comments held out from training.
