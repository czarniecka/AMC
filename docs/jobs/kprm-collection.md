# KPRM job advertisements: pilot collection

Source: archived (closed) advertisements on https://nabory.kprm.gov.pl, public civil
service recruitment. The site's `robots.txt` has an empty `Disallow`. Requests are
throttled (default 2 s), retried with backoff and identified by a User-Agent; set
`KPRM_USER_AGENT` in `.env` or the environment to include your contact details.

## How the sample is drawn

Advertisement IDs grow with publication date, and a page can be fetched by ID alone
(`/a/b/c,{ID},v8`). The pilot draws a seeded random sample of IDs inside four
half-year windows (2021-H2, 2022-H1, 2023-H2, 2025-H2), 50 per window by default.
Window boundaries are found by binary search on publication dates. IDs that do not
exist are marked `missing`, so windows can end with slightly fewer than 50 ads.
The manifest is never redrawn for a window that already has rows.

```text
python scripts/jobs/collect_ads.py --sample-only   # build manifest only
python scripts/jobs/collect_ads.py                 # fetch pending ads, resumable
python scripts/jobs/collect_ads.py --limit 20      # fetch at most 20
```

Raw HTML is cached in `data/jobs/raw/` so the parser can be improved without new requests.

## CSV contract (`data/jobs/`, UTF-8 with BOM, not committed)

| File | Fields |
| --- | --- |
| `kprm_sample.csv` | ad_id, window, status (`pending`, `ok`, `missing`) |
| `kprm_ads.csv` | ad_id, published_at, valid_until, title, institution, unit, city, positions, work_time, salary_text |
| `kprm_ad_texts.csv` | ad_id, tasks, requirements_required, requirements_optional |

Text sections keep one list item per line. Requirement sections include statutory
boilerplate (citizenship, public rights, lustration statement); ignore it when counting
skills. `work_time` is the full-time fraction as shown on the site.

## Limitations

- Public administration only; advertisements are formal and often template-based.
- Half-year windows differ in volume (about 10 thousand ads in 2021-H2, about 6 thousand in 2025-H2).
- 200 ads are enough for building the codebook, not for statistical tests.
