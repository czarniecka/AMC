# Mapping requirement fragments to ESCO

Each requirement fragment is embedded with a multilingual model and matched to the nearest
ESCO skill labels by cosine similarity. A match counts only above a similarity threshold that
is calibrated on hand-reviewed proposals.

## Prerequisites

- ESCO skills downloaded: see [ESCO skills](esco.md).
- Ollama running with an embedding model: `ollama pull bge-m3` (default; override with
  `ESCO_EMBED_MODEL`). `OLLAMA_BASE_URL` selects the service, as for classification.
- `numpy`, which is installed through `streamlit`. Run `uv add numpy` once to declare it in
  `pyproject.toml` and `uv.lock`.

## Steps

```text
python scripts/esco/map_fragments.py build-index    # embeds ~16k ESCO labels, resumable
python scripts/esco/map_fragments.py match          # top-3 skills per fragment, all ads
python scripts/esco/map_fragments.py review-sheet   # after the 150 fragments are labeled
python scripts/esco/map_fragments.py calibrate      # after the review sheet is filled in
```

- `build-index` stores one vector per preferred and alternative label under
  `data/esco/index/<model>/`. Finished chunks are kept, so an interrupted run resumes.
  Changing the model gives a separate index.
- `match` writes `data/jobs/analysis/esco_matches.csv` with `ad_id`, `period`, `line`, `text`, `rank`,
  `uri`, `label`, `score` and `group_code`. A skill's score is its best label. Fragment text
  includes the lead-in of its list, for example "Znajomość: Kodeksu cywilnego".
- `review-sheet` refuses to run until every fragment in `label_sheet.csv` has a `type`, and
  never overwrites an existing review sheet. It writes `esco_review.csv` (to be judged) and
  `esco_review_key.csv` (scores, kept out of sight).
- `calibrate` reads the `best` column and prints precision, recall and F1 for each threshold
  (also saved to `esco_threshold_table.csv`). `--min-precision` (default 0.8) selects the
  highest-F1 threshold that keeps precision at that level.

## Interpreting results

- Recall is measured against proposals judged correct. Fragments with no true ESCO
  counterpart, such as references to a specific statute, can only lower precision.
- Top-3 hit rate shows how often the right skill is among the candidates even when it is not
  ranked first.
- The same threshold is applied to all periods. Report the threshold with any scope figures,
  because the number of matched skills per ad depends on it.

## Limitations

- ESCO labels are verb phrases about occupations ("współpracować z...") and cover legal or
  administrative knowledge weakly. Expect many fragments to stay unmatched.
- About 3% of ESCO skills are missing from the download (see [ESCO skills](esco.md)).
- Descriptions are not embedded, only labels; only 1,362 skills have Polish alternative labels.
- 150 reviewed fragments give a rough threshold, not a precise one.
