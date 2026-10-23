# Hand-labeling guide (150 fragments)

File: `data/jobs/labeling/label_sheet.csv` (UTF-8 with BOM; open in Excel or Google Sheets and
keep CSV format). Fill the `type`, `categories` and optional `note` columns.

```text
python scripts/jobs/make_label_sheet.py   # refuses to overwrite an existing sheet
```

The sheet is blind: it has no period, no ad ID and no suggestions from the codebook or ESCO.
`label_key.csv` (same folder) maps fragments to ads and periods; **do not open it** until
all fragments are labeled. The fragments are a seeded random draw, 75 per period
(before 2023 and 2023 onward), at most 3 per ad, with statutory boilerplate removed.
A fragment is one comma/semicolon-separated part of a requirement line; read
`context_line` when the fragment is only a continuation of a list.

## `type` (one value)

| Value | Use for |
| --- | --- |
| `competence` | a skill, knowledge, ability or personal attribute the candidate must have (for example "komunikatywność", "znajomość ustawy o finansach publicznych") |
| `formal` | education level or field, driving licence, professional licence, years of experience, completed course or training, clearance |
| `other` | not a requirement of the candidate, or too fragmentary to judge even with the context line |

## `categories` (only when `type` is `competence`)

Use one or more of the values below separated by `;`, or `none` if no category fits.
If a fragment names two different skills, list both categories. Label by meaning, not by
keywords: "biegła obsługa arkuszy kalkulacyjnych" is `digital_basic`.

| Value | Meaning |
| --- | --- |
| `digital_basic` | everyday computer, office suite, spreadsheet, internet use |
| `digital_advanced` | databases, programming, IT systems administration, e-services, cybersecurity |
| `data_analysis` | working with data, statistics, reporting, indicators, evaluation |
| `analytical_thinking` | analytical thinking, drawing conclusions, logic, analysis in general |
| `ai_automation` | AI, machine learning, automation, algorithms |
| `foreign_language` | foreign language knowledge or level |
| `legal_knowledge` | knowledge of laws, regulations, codes, procedures |
| `domain_knowledge` | specialist knowledge of a field other than law (veterinary, geology, finance, ...) |
| `communication` | communication, negotiation, presentation, assertiveness |
| `teamwork` | cooperation, working in a team |
| `self_organisation` | work organisation, independence, punctuality, reliability, diligence |
| `stress_resilience` | stress resistance, resilience, flexibility, readiness for change |
| `learning_development` | willingness to learn, professional development |
| `leadership_management` | managing people or teams, leadership |
| `project_management` | project management, schedules, EU funds |
| `creativity_initiative` | creativity, initiative, innovation |
| `customer_service` | client service, handling visitors, professional conduct towards clients |

If a competence fits none of them, use `none` and describe it in `note`; those notes show what
the codebook is missing. Use `note` also for uncertainty ("unsure") or an ESCO skill you
recognise.

## Status and versioning

Both sheets are fully labeled by a single coder: `label_sheet.csv` (150 fragments) and
`esco_review.csv` (91 competence fragments). They are the gold standard for the codebook
and the ESCO threshold and are versioned in Git together with their keys. Do not edit
them in place; a new labeling round gets a new file. `*.excel_backup.csv` copies are
not versioned. Agreement between two coders (Cohen's kappa) has not been measured yet.

## Next stage

After the sheet is labeled, the ESCO matcher proposes the three closest ESCO skills for every
`competence` fragment (`esco_review.csv`, scores hidden). In the `best` column enter `1`, `2`
or `3` for the candidate that expresses the same requirement, or `none` if no candidate does.
Use `note` for "partly" matches. That pass calibrates the similarity threshold; see
[ESCO mapping](esco-mapping.md). It is shown only after this first labeling so that the
proposals cannot influence it.
