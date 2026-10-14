# ESCO skills (Polish)

Reference taxonomy for mapping requirement fragments to competences.

```text
python scripts/esco/fetch_skills.py
```

Output in `data/esco/` (not committed): `esco_skills_pl.csv` with `uri`, `preferred_label`,
`alt_labels`, `description`, `skill_type` (`umiejętność` or `wiedza`), `reuse_level`,
`group_code`, `group_title`. Cached intermediate files are in `groups/` and `batches/`;
an interrupted run resumes from them.

## How it is downloaded

The portal's download form is an interactive multi-step form, so the script uses the
official public web service (`ec.europa.eu/esco/api`) instead. The service limits listing
and search to the first 200 results, so the script walks the concept tree from the four
top concepts (knowledge, language skills, skills, attitudes) and fetches details by URI in
batches of 50, with a 1 s delay between requests. The service does not report its dataset
version; the download portal lists v1.2.1 (December 2025) as the latest release. Record the
download date next to any results.

## Known gaps (downloaded 2026-10-13)

- 13,088 skills saved. The search endpoint reports 13,485 active skills, so about 3% are missing.
- Group `S1.5.3` (a sibling of the "consulting and advice" groups) returns HTTP 500 from
  the service; its skills are absent. The group is listed in `skipped_groups.json`.
- Six skills return HTTP 500 individually and are listed in `skipped_skills.json`.
- `group_code` is empty for 2,830 rows (mostly knowledge concepts), which the service does
  not link through `broaderHierarchyConcept`.
- Only 1,362 skills have Polish alternative labels, so most matching must rely on the
  preferred label and description.

## Licence

ESCO is published by the European Commission and may be reused with attribution
(https://esco.ec.europa.eu). Cite the ESCO version and the download date.
