# Skill scope before and after 2023

Question: did the range of skills required in KPRM advertisements widen after 2023?
Keyword counts alone (for example "AI") cannot answer this, so the analysis measures
breadth with a codebook and compares two periods.

```text
python scripts/jobs/analyze_skills.py
```

Outputs in `data/jobs/analysis/`: `skill_flags.csv` (one row per ad), `skill_summary.csv`
(share per category and Holm-adjusted p) and `scope_summary.csv`.

## Method

- **Periods:** `pre` is published before 2023-01-01, `post` is 2023 onward
  (pilot windows 2021-H2 and 2022-H1 versus 2023-H2 and 2025-H2). The cut-off is
  `CUTOFF` in `amc/jobs/analysis.py`.
- **Text:** requirement lines (required and optional) only; tasks are not used.
- **Codebook:** `config/jobs/skill_codebook.json`. Each line is dropped if it is statutory
  boilerplate or a formal condition (education, driving licence, experience, courses).
  Remaining lines are matched against skill categories by regular expressions.
- **Scope measures:** number of distinct skill categories per ad, and number of
  substantive requirement lines per ad.
- **Tests:** permutation test on the post-minus-pre mean difference, also stratified by
  institution group (veterinary, police, tax/customs, central ministries, other) to
  separate wider scope from a changed mix of employers; bootstrap interval for the
  difference; Fisher exact test per category with Holm correction.

## ESCO measures

If `data/jobs/analysis/esco_matches.csv` exists, the analysis adds two scope measures:
distinct ESCO skills and distinct ESCO skill groups (first two levels of the group code) per
ad. Only top-1 matches with a score of at least `--esco-threshold` (default 0.736, from
`map_fragments.py calibrate`) count, and fragments of formal lines are skipped. The
threshold keeps about 81% precision but only about half of the correct matches, so the
ESCO counts understate scope; compare periods, not absolute values. Rerun
`map_fragments.py match` after changing the codebook.

## Limitations

- About 96 ads per period, so tests are exploratory; only large effects are detectable.
- Matching is per line. Lines that list several skills count once per category, and
  one line can match several categories. Changing a regex changes the results, so keep
  the codebook version with any reported numbers.
- Regexes have not yet been validated against hand labels. Label a random subset of
  lines and report precision and recall per category before drawing conclusions.
- A higher line count can reflect longer templates rather than more skills.
- The sample covers public administration only, and 2024 is not in the pilot.
