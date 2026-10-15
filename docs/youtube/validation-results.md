# YouTube pilot validation: single annotator

## Completed scope

The current validation uses 50 comments from five videos, sampled with seed
20261015. Codebook 1.0.0 remains unchanged. The reference is
`data/youtube/labeling/pilot_gold_single_v2.csv`, derived from annotator A's revised
pilot sheet. Annotator B is not used. No agreement between independent annotators
has been measured. The 200-comment evaluation sample is unused and is not part
of the completed validation. No further annotation is required for this pilot.

This reference has undergone model-informed review: the tool selected comments
where the initial human labels disagreed with Qwen. Model label values were hidden,
but selection itself can influence subsequent judgments. The report explicitly
marks this as non-independent, developmental validation. Do not describe it as a
held-out test or evidence that Qwen is 92% accurate on new comments.

## Model and reproducibility

- Model tag: `qwen3:8b`.
- Prompt SHA-256: `12029728a1d797f8dbdf08d69208a967ea10d6a11a751a5bdba3626e0a7f7e84`.
- The existing predictions were reused; the model/prompt was not changed.
- Codebook definitions are human annotation rules; they are not all implemented
  verbatim in the historical model prompt.
- Sample manifest records source/key/codebook fingerprints and the sampling policy.
- Reports record the gold, prediction and key fingerprints. Model tags are mutable;
  classification CSVs do not record an immutable model digest. The earlier runtime
  benchmark recorded installed model ID `500a1f067a9f` and Ollama 0.40.2, but these
  values alone cannot certify the origin of every row in the prediction file.

## Results

| Assessment | Initial human reference | Revised human reference |
| --- | ---: | ---: |
| Relevance agreement, all 50 | 40/50 (80%) | 46/50 (92%) |
| Impact agreement, all 50 | 22/50 (44%) | 46/50 (92%) |
| Impact agreement, human-relevant subset | 5/26 (19.2%) | 27/30 (90%) |

Revised-reference macro-F1: relevance 0.917, impact 0.880. The relevance `unclear`
class is absent from both reference and predictions, so its metrics are undefined
and excluded from this macro average. These averages therefore do not validate
all possible classes. The two human-relevant subsets above differ in composition.

The reviewer changed 24 of the 50 comments: relevance changed in eight and impact
in 24. The UI marked 27 comments as reviewed against model disagreement. Human
`mixed` labels increased from two to 19. This is a change of reference annotations,
not a measured improvement to the unchanged classifier.

Revised impact classes have supports: positive 4, negative 5, mixed 19, neutral 2,
unclear 20. Small classes cannot support strong class-specific reliability claims.
Interpret overall impact agreement alongside the relevant-only result, because
unrelated comments are assigned unclear impact mechanically.

## Reproduce and inspect

```text
uv run --locked python scripts/youtube/validate_comments.py evaluate --gold data/youtube/labeling/pilot_gold_single_v2.csv --split pilot --model qwen3:8b --prompt-hash 12029728a1d797f8dbdf08d69208a967ea10d6a11a751a5bdba3626e0a7f7e84 --output data/youtube/analysis/pilot_validation_single_v2.json
```

Use a NEW output name if that report already exists. The script refuses to replace
any existing output. Beside JSON, it writes `.metrics.csv`, `.confusion.csv` and
`.disagreements.csv`. The metrics table follows the job-offer validation layout:
applied_to, category, gold, tp, fp, fn, precision, recall, with F1 added. Empty metric
cells mean undefined, not zero. The disagreement table contains sample IDs and
human/model labels, without duplicating comment text.

Keep the initial report `pilot_validation_single_v1.json` and original gold file
as the baseline. Corrections or new model runs require a new version, not replacing
prior results. No human labels were fabricated and no model predictions were edited.

## Research interpretation

This pilot documents agreement with one reviewed human reference within the
collected sample. It is suitable for developing annotation rules and identifying
errors. It does not establish independent generalization performance, annotator
reliability, population sentiment, or causal effects of AI on work. Any later
independent quality claim requires a new blind evaluation, which is outside the
current completed scope.
