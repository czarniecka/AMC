# YouTube comment annotation and validation

## Purpose and scope

The versioned codebook is `config/youtube/comment_codebook.json`. It defines the
author's expressed assessment of AI's impact on work, employment and occupational
skills. This is targeted assessment, not general sentiment or fact checking.
The unit is one top-level comment. Do not use video titles, other comments or
model predictions to guess missing context. Personal experiences and predictions
can both be coded, but these labels do not establish real labor-market effects.

The existing job-offer codebook extracts skills using regexes. This codebook
instead defines human labels against which the LLM is evaluated. Existing Qwen
predictions are not a gold standard, and the current model prompt has not been
automatically replaced by this new codebook. Start by measuring it as a baseline.

## Labels

First decide `relevance`:

- `relevant`: AI and employment, workplace tasks or occupational competencies.
- `unrelated`: outside that target, including video praise and resource requests.
- `unclear`: insufficient context to decide whether it addresses that target.

Then decide `impact`:

- `positive`: expressed benefit without expressed harm.
- `negative`: expressed harm, worry or threat without expressed benefit.
- `mixed`: both expressed benefit and harm, regardless of which is stronger.
- `neutral`: relevant description/question with no expressed evaluation.
- `unclear`: evaluation cannot be interpreted. Mandatory if relevance is
  `unrelated` or `unclear`.

Mentioning training is not itself pressure or enthusiasm. A factual question
about job loss is not automatically negative; expressed fear is. General irony
without enough textual cues is unclear. Never use outside assumptions to label it.
The JSON codebook includes invented Polish and English examples and edge rules.
Annotators must understand the text's language; discuss unfamiliar languages
before assigning final labels. Do not translate through the classifier being tested.

## 1. Prepare frozen samples

```text
uv run --locked python scripts/youtube/validate_comments.py prepare
```

Default output: `data/youtube/labeling/`. This creates:

- `pilot_annotator_a.csv`, `pilot_annotator_b.csv`: 50 comments for development.
- `evaluation_annotator_a.csv`, `evaluation_annotator_b.csv`: 200 held-out comments.
- `sample_key.csv`: private mapping to source IDs, text hashes and splits.
- `manifest.json` and `codebook.json`: seed, source fingerprint, policy and frozen
  codebook version. Preserve these with the annotation files.

No predictions are read. Sheets show only an anonymous sample ID, the comment,
two blank label fields and a note field. Do not give annotators the key or model
output. Separate videos are used for pilot and evaluation; exact duplicate texts
are removed before sampling. Language is NOT automatically inferred or balanced.
The sample describes this collected pool, not the population of YouTube users.
Inspect language coverage manually and document limitations. Held-out videos make
the final test more conservative than a random split of comments from the same film.

The command refuses to overwrite an existing directory. Use `--output` for a new
version, and `--pilot`, `--evaluation`, `--seed` to change sampling. Do not redraw
samples just because results are poor. CSVs use UTF-8 BOM and comma delimiters;
preserve original comment cells and spreadsheet-safety apostrophes.

## 2. Independent human annotation

### Button-only browser tool

During pilot error analysis, enable **Only disagreements with Ollama**. Choose one
model/prompt cohort. Only completed human labels with different predictions are
shown; matching uses frozen IDs and text hashes. AI label values remain hidden.
The evaluation split disables this option. Saves in review mode append a
`[model-informed pilot review]` note. Keep the initial gold/report as the baseline;
revised pilot scores are development results, not an independent model-quality test.

Run `make annotate` or `uv run --locked python scripts/run_annotation.py` and open
http://localhost:18502. This standalone tool needs no Ollama, model or API key.
Alternatively select Annotate in the existing web application's page sidebar.
Choose your A/B sheet, click a relevance option and (for relevant comments) an
impact option, then Save & next. No typing is needed except an optional note.
There is no default answer for a blank comment. Unrelated/unclear relevance sets
impact to unclear automatically. Progress is saved to the selected CSV after
each Save, and the next session starts at the first unfinished comment.
Previous/Skip navigate without committing unsaved choices. Saved labels can be
revisited and corrected. Before the first edit the original sheet is backed up;
concurrent changes are detected rather than silently overwritten. Assign each
annotator their own file. The UI is a trusted local tool, not an access-controlled
multi-user service: separate sheets prevent accidental mixing, not deliberate
inspection of another person's work. The Docker web service mounts only the
labeling directory for persistence; rebuild/recreate it after installing this page.

Give A and B their respective PILOT sheets. Each independently fills `relevance`
and `impact` using exact label names; `note` is optional. Do not show them each
other's answers or the classifier's labels. Preserve their separate originals.

Pilot disagreements reveal ambiguous rules. Discuss them, revise the codebook
and prompt if needed, then freeze a new annotation version before the final test.
Do not tune on evaluation labels. If the rules change, re-annotate consistently;
do not mix versions in one gold file. The final evaluation sheets should remain
unopened for model development. A coordinator may distribute them to independent
annotators after the protocol is frozen, while withholding them from the developer.

## 3. Adjudication and gold standard

```text
uv run --locked python scripts/youtube/validate_comments.py adjudicate --a data/youtube/labeling/pilot_annotator_a.csv --b data/youtube/labeling/pilot_annotator_b.csv --output data/youtube/labeling/pilot_gold.csv
```

The command requires complete labels from both annotators and identical IDs/text.
It prints initial exact agreement per field. The output retains both original
ratings and notes. Agreed labels are copied into final fields; disagreements stay
blank. A human reviewer resolves disagreements and records `reviewer`,
`reviewed_at` (prefer ISO date) and `resolution_note`. Confirm reviewer/date for
EVERY row, including agreements. Keep cases genuinely ambiguous as `unclear`;
do not force a positive/negative decision. A gold file is ready only when these
fields and both final labels are complete. The software never invents human gold.

Repeat for `evaluation_annotator_a.csv` and `evaluation_annotator_b.csv`, creating
`evaluation_gold.csv`, AFTER completing pilot development and freezing the protocol.
Initial agreement is a useful check, not proof of annotation correctness.

## 4. Evaluate one model/prompt cohort

### Single-annotator alternative

If a second independent annotator is unavailable, keep B blank. Use A's completed
sheet as a single-annotator reference rather than duplicating ratings:

```text
uv run --locked python scripts/youtube/validate_comments.py single-gold --sheet data/youtube/labeling/pilot_annotator_a.csv --output data/youtube/labeling/pilot_gold_single.csv --annotator annotator_a
```

The command validates complete labels and frozen sample identities/text hashes.
It preserves the original sheet and records `annotation_method=single_annotator`.
`reviewed_at` records import/confirmation time, not the original annotation time.
Reports identify this limitation; no inter-annotator agreement can be reported.
For pilot validation use `--gold .../pilot_gold_single.csv --split pilot`.
Pilot scores remain developmental, not an independent final evaluation.

```text
uv run --locked python scripts/youtube/validate_comments.py evaluate --gold data/youtube/labeling/evaluation_gold.csv --model qwen3:8b --prompt-hash YOUR_FULL_PROMPT_HASH --output data/youtube/labeling/evaluation_report.json
```

Copy the full `prompt_hash` from the intended classification run; use `--predictions`
for another predictions file and `--split pilot` for development reports. Supply
the corresponding `--key` when using a different labeling directory. Re-run the
classifier separately if predictions are missing. Evaluation does not invoke Ollama.

The report includes accuracy, per-class precision/recall/F1/support and confusion
matrices for both fields. `impact_on_gold_relevant` isolates impact performance
among truly relevant comments while retaining errors caused by the relevance gate.
Undefined values are null, not zero; macro-F1 averages classes present in gold or
predictions. A class with no examples cannot be claimed as validated.

Evaluation rejects missing/duplicate predictions, changed texts, unfinished gold
and inconsistent labels. It requires exact sample coverage and one selected model
tag/prompt hash; it never silently reports only the comments that happened to match.
Reports are not overwritten. Preserve source/model/codebook versions with results.
Current classification CSVs record model tags, not immutable weight digests; record
the installed digest and Ollama version separately for reproducibility.

The benchmark of runtime is not a quality evaluation. Until humans finish these
sheets, no accuracy or validated gold standard exists. Do not commit meeting notes
or annotator identities without review; labeling files live under ignored `data/`.
