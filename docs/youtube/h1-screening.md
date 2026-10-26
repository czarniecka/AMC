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

## Run GPT-6 Luna with OpenAI Batch API

Set `OPENAI_API_KEY` in your private `.env` or environment. Sending comments to
this API transfers their text to an external provider and incurs API charges.
Start with a one-request pilot. The first command only prepares the real OpenAI
Batch API request file; `submit` uploads it and creates an asynchronous job:

```text
uv run --locked python scripts/youtube/run_screening.py prepare --input-dir data/youtube/screening/work_v1 --run-dir data/youtube/screening/work_v1/luna_pilot --limit-batches 1
uv run --locked python scripts/youtube/run_screening.py submit --run-dir data/youtube/screening/work_v1/luna_pilot
uv run --locked python scripts/youtube/run_screening.py status --run-dir data/youtube/screening/work_v1/luna_pilot
uv run --locked python scripts/youtube/run_screening.py fetch --input-dir data/youtube/screening/work_v1 --run-dir data/youtube/screening/work_v1/luna_pilot
```

Run `status` again until the job is complete, then run `fetch`. Inspect
`luna_pilot/predictions.jsonl` and `validation_report.json`. For all prepared
batches, create a **different** run directory with `--skip-batches 1` and omit
`--limit-batches` from `prepare`; then repeat submit/status/fetch. This sends
only the remaining groups after the pilot. `submit` does
not create a second job after recording a Batch ID. `fetch` downloads provider
output and error files, validates every returned comment ID and writes only
validated predictions. Missing or failed requests are counted in the report.
Each prediction retains its API `usage`, and `validation_report.json` sums input,
output, cached-input, cache-write and reasoning tokens across valid responses.

The request uses a stable `prompt_cache_key` based on the instruction hash and an
explicit cache breakpoint after the fixed instruction. Comment text comes after
that breakpoint. GPT-6 Luna routes cache automatically; the key is useful for
accounting, not a guarantee of hits. The current fixed instruction is shorter
than the 1024-token minimum cacheable prefix, so `cached_input_tokens` may be
zero. Keep the instruction useful and stable; do not pad it just to get hits.
The response usage fields, rather than the key, show actual reuse.

OpenAI's Batch API itself requires JSONL, with one API request per line and a
unique `custom_id`. The runner converts the project's comment-group JSONL into
that required format (`requests.jsonl`), uploads it through the Files API and
submits it to the `/v1/responses` Batch endpoint. Each API request still carries
up to 100 comments, so the current 283 prepared groups form 283 Batch requests.

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
