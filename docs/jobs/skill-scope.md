# Skill scope before and after 2023

Question: did the range of skills required in KPRM advertisements widen after 2023?
Keyword counts alone (for example "AI") cannot answer this, so the analysis measures
breadth with a codebook and compares two periods.

```text
python scripts/jobs/analyze_skills.py
```

Outputs in `data/jobs/analysis/`: `skill_flags.csv` (one row per ad), `skill_summary.csv`
(share per category and Holm-adjusted p) and `scope_summary.csv`.
The summaries, the gold standard and the validation tables are versioned in Git
(see [Versioned data](../operations.md#versioned-research-data)).

## Method

- **Periods:** `pre` is published before 2023-01-01, `post` is 2023 onward
  (pilot windows 2021-H2 and 2022-H1 versus 2023-H2 and 2025-H2). The cut-off is
  `CUTOFF` in `amc/jobs/analysis.py`.
- **Text:** requirement lines (required and optional) only; tasks are not used.
- **Codebook:** `config/jobs/skill_codebook.json`. Each line is dropped if it is statutory
  boilerplate or a formal condition (education, driving licence, experience, courses).
  Remaining lines are split into fragments (comma/semicolon-separated parts, with the
  lead-in before an early colon) and each fragment is matched against skill categories by
  regular expressions. The boilerplate and formal filters see the whole line; the skill
  regexes see only the fragment. `fragment_decision` in `amc/jobs/analysis.py` is the single
  implementation, used by the analysis and by the validation script.
- **Scope measures:** number of distinct skill categories per ad, and number of
  substantive requirement lines per ad.
- **Tests:** permutation test on the post-minus-pre mean difference, also stratified by
  institution group (veterinary, police, tax/customs, central ministries, other) to
  separate wider scope from a changed mix of employers; bootstrap interval for the
  difference; Fisher exact test per category with Holm correction.

## Validation against hand labels

Gold standard: 150 hand-labeled fragments (75 per period, seeded draw, blind sheet), see the
[labeling guide](labeling-guide.md). Of these, 91 are `competence` and 59 are `formal`.

```text
python scripts/jobs/validate_codebook.py
```

Output: `data/jobs/analysis/codebook_validation.csv` (versioned, with the codebook version).
The script applies exactly the decision used by the analysis (`fragment_decision`), so the
unit of validation equals the unit of measurement. Earlier versions (codebook 2) matched
whole lines in the analysis but were validated on fragments; the labels cover only the
sampled fragment of a line, so a line-level comparison would have counted correct hits on
unlabeled sibling fragments as false positives. Moving the analysis to fragments removed
that mismatch; ad-level results barely changed (post-minus-pre difference in distinct
categories per ad 0.458 -> 0.448, permutation p 0.222 -> 0.226; no category stays below 0.05
after Holm correction before or after).

Codebook version 3, precision and recall per category:

| Category | Gold | Precision | Recall |
| --- | ---: | ---: | ---: |
| `legal_knowledge` | 32 | 1.00 | 0.94 |
| `self_organisation` | 15 | 1.00 | 1.00 |
| `communication` | 13 | 1.00 | 0.92 |
| `digital_basic` | 7 | 1.00 | 0.86 |
| `teamwork` | 6 | 1.00 | 0.83 |
| `stress_resilience` | 5 | 1.00 | 1.00 |
| `foreign_language` | 4 | 1.00 | 1.00 |
| `domain_knowledge` | 4 | 1.00 | 0.50 |
| `digital_advanced` | 2 | 1.00 | 1.00 |
| `data_analysis`, `learning_development`, `project_management`, `customer_service` | 1 each | 1.00 | 1.00 |
| `analytical_thinking`, `leadership_management` | 1 each | n/a | 0.00 |
| `ai_automation`, `creativity_initiative` | 0 | n/a | n/a |

The formal/boilerplate filter drops 58 of 59 formal fragments and wrongly drops 1 of 91
competences.

Reading the table:

- **These figures are in-sample.** Version 3 fixed the errors seen in these same 150
  fragments (for example `statystyczn`, `zwięzł`, `protokołowan`, a narrower
  `znajomość zasad`, and `organ… administracji` as legal knowledge). Precision of 1.00 is
  therefore optimistic. Confirm on a fresh labeled sample before reporting it.
- Categories with fewer than about 10 gold cases are not validated; `ai_automation` and
  `creativity_initiative` have no gold case at all, so the share of ads with AI skills
  (0 in both periods) is unverified in both directions.
- Known remaining misses are context-dependent: multi-category fragments (for example
  "Organizacja pracy i orientacja na osiąganie celów"), "zarządzanie zasobami" and
  fragments whose meaning comes from the context line only. Regexes cannot fix these
  without overfitting.
- Not done: a second coder and Cohen's kappa; a split between a tuning set and a test set.

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
- Matching is per fragment. A category counts once per ad, and one fragment can match
  several categories. Changing a regex changes the results, so keep
  the codebook version with any reported numbers.
- Validation (below) rests on one coder and 150 fragments; several categories have
  0-4 gold cases, so their precision and recall are not interpretable.
- A higher line count can reflect longer templates rather than more skills.
- The sample covers public administration only, and 2024 is not in the pilot.
