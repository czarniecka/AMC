# H1 comment screening batches

H1 asks whether the share of online comments expressing concern about job security
in the face of AI grows after the November 2022 ChatGPT release. The unit is a
comment, not a video. The preparation script does not call a model; the separate
runner below does. H2 concerns job advertisements and is handled separately.

Collect the current pre/post work-topic sample, then prepare exactly 25000
comments from each period:

```text
uv run --locked python scripts/youtube/collect_random_sample.py collect --target 50000 --seed 20261025
uv run --locked python scripts/youtube/collect_random_sample.py status
uv run --locked python scripts/youtube/prepare_screening.py --database data/youtube/work_sample_v3/sample.sqlite3 --per-period 25000 --output data/youtube/screening/work_v3_50k_stage1_v1
```

The older reviewed-video pilot can still be prepared from its CSV by omitting
`--database` and choosing another output directory. Keep these two collection
frames separate; their comments can overlap and their selection rules differ.
The existing `work_sample_v2` database is an archive collected with an older
query list and protocol. The default collector database is now
`data/youtube/work_sample_v3/sample.sqlite3`. Repeat `collect` if an API request
limit stops the run before both periods reach 25000 comments. The collector may
overshoot a quota by one API page; selection is seeded and recorded in the
manifest. `--per-period` fails if either period is short.

The output directory must be new. `batches.jsonl` contains one JSON object per
line, with up to 100 comments, each carrying a short `id` and its text. Batches
also stop before `--max-batch-chars` (default 30000) to avoid oversized requests.
The script shuffles comments reproducibly (`--seed 42`). It keeps repeated text
from different comments because H1 concerns the share of actual comments.

`screening_config.json` contains the exact screening instruction, an example
response, source file hash and counts. The runner sends the instruction and one
line of `batches.jsonl` per request. It requires one JSON response containing
`batch_id` and `labels` with one entry per input `id`. Each label has
`ai` and `work` (`yes`/`no`) plus `stance`
(`threat`/`reassurance`/`opportunity`/`mixed`/`none`). A work-only comment is
`ai=no, work=yes, stance=none` and remains in the pre/post sample. This matches
[stage 1 annotation guidelines](annotation-guidelines.md). Stage 2 labels
(`attitude`, `threat_type`, `competence_claim`, `sector`) apply later only to
comments with `ai=yes` and `work=yes`; see
[stage 2 guidelines](annotation-guidelines-stage2.md).
Malformed or incomplete responses stop the run; rerun after checking the error.
Completed batches are skipped.

## Run GPT-6 Luna with OpenAI Batch API

Set `OPENAI_API_KEY` in your private `.env` or environment. Sending comments to
this API transfers their text to an external provider and incurs API charges.
Start with a one-request pilot. The first command only prepares the real OpenAI
Batch API request file; `submit` uploads it and creates an asynchronous job:

```text
uv run --locked python scripts/youtube/run_screening.py prepare --input-dir data/youtube/screening/work_v3_50k_stage1_v1 --run-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_pilot --limit-batches 1
uv run --locked python scripts/youtube/run_screening.py submit --run-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_pilot
uv run --locked python scripts/youtube/run_screening.py status --run-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_pilot
uv run --locked python scripts/youtube/run_screening.py fetch --input-dir data/youtube/screening/work_v3_50k_stage1_v1 --run-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_pilot
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
output, cached-input, cache-write and reasoning tokens across valid responses. It
also counts requests with at least one cached input token.

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
up to 100 comments, so this 50000-comment sample has 500 Batch requests.

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

## Direct Responses API pilot for the stage 1 labels

Earlier pilots used the provisional `h1_related`/`job_security_concern` labels.
Their outputs remain archived and can still be validated with the older schema.
The current `work_v3_50k_stage1_v1` snapshot uses the same 50000 comments and
order but asks for the separate `ai`, `work`, and `stance` labels from the
annotation guidelines. This preserves work-only comments in both periods.
Generic robots or automation without a clear AI reference get `ai=no` under
those guidelines.

To test the current prompt without Batch API scheduling, use the already prepared
`work_v3_50k_stage1_v1/luna_pilot` request file. This command makes **one paid
Responses API request containing 100 comments**, saves validated predictions,
and can be rerun without repeating successful groups:

```text
uv run --locked python scripts/youtube/run_screening_direct.py \
  --request-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_pilot \
  --output-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_pilot_direct \
  --workers 1
```

Inspect `luna_pilot_direct/predictions.jsonl` and `validation_report.json` before
screening the remainder. Because earlier instructions were adjusted after inspecting
the first 100 comments, also test the separately prepared `luna_holdout` request
(the next 100 comments) before the full run:

```text
uv run --locked python scripts/youtube/run_screening_direct.py \
  --request-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_holdout \
  --output-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_holdout_direct \
  --workers 1
```

If both sets of revised labels are acceptable, prepare requests
for the other 498 groups and send them with bounded concurrency:

```text
uv run --locked python scripts/youtube/run_screening.py prepare \
  --input-dir data/youtube/screening/work_v3_50k_stage1_v1 \
  --run-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_remaining \
  --skip-batches 2
uv run --locked python scripts/youtube/run_screening_direct.py \
  --request-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_remaining \
  --output-dir data/youtube/screening/work_v3_50k_stage1_v1/luna_remaining_direct \
  --workers 4
```

Do not submit the same `luna_remaining` requests through Batch API as well: that
would label and bill for the same comments twice. Direct requests use the usual
Responses API pricing and rate limits rather than Batch pricing. On transient
rate limits or server errors, the direct runner follows `Retry-After` when given,
then retries with backoff. Successful groups are stored individually for resume.
If a model response lacks a valid text output or has inconsistent labels, the
runner records that group's failure in `failures/`, stores the provider body in
`raw_responses/`, continues with other groups, and leaves it out of
`predictions.jsonl`. Repeating the same command skips saved successes and recorded
failures. Read timeouts are also recorded because the server may have completed
the request after the client disconnected. Use `--retry-failed` only when you
deliberately want to pay for another attempt at those failed groups.
