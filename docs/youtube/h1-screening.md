# H1 comment screening batches

H1 asks whether the share of online comments expressing concern about job security
in the face of AI grows after the November 2022 ChatGPT release. The unit is a
comment, not a video. This preparation script does not label comments or call a
model. H2 concerns job advertisements and is handled separately.

Use the pre/post work-topic sample on this branch for the H1 comparison:

```text
uv run --locked python scripts/youtube/prepare_screening.py --database data/youtube/work_sample_v2/sample.sqlite3 --output data/youtube/screening/work_v1
```

The older reviewed-video pilot can still be prepared from its CSV by omitting
`--database` and choosing another output directory. Keep these two collection
frames separate; their comments can overlap and their selection rules differ.

The output directory must be new. `batches.jsonl` contains one JSON object per
line, with up to 100 comments, each carrying a short `id` and its text. Batches
also stop before `--max-batch-chars` (default 30000) to avoid oversized requests.
The script shuffles comments reproducibly (`--seed 42`). It keeps repeated text
from different comments because H1 concerns the share of actual comments.

`screening_config.json` contains the exact screening instruction, an example
response, source file hash and counts. Send the instruction as the system message
and one line of `batches.jsonl` as the user message to a small model. Ask for a
single JSON response containing `batch_id` and `labels` with one entry per input
`id`. Each label has `h1_related` and `job_security_concern`, both `yes`, `no`, or
`unclear`. Check that every input ID occurs exactly once before joining results.
Retry malformed or incomplete batches; never silently accept partial labels.

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
