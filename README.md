# AMC Project

YouTube comment collection and local classification with Ollama/Qwen, plus job
advertisements (KPRM civil service, Hacker News "Who is hiring?") and Wykop posts.
Results accumulate in CSV files. Classification returns `relevance` and `impact`.

## Start with Docker

Copy `.env.example` to `.env` and enter the YouTube key privately if collecting.
Install Docker, then start the web application:

```text
docker compose up --build -d web
```

Open http://localhost:18501. The first start downloads Ollama and the selected
model; subsequent starts reuse the model volume. Python and uv are included in
the application image. NVIDIA GPU is optional; see the operations guide.

## Run scripts

With uv installed:

```text
uv sync --locked
uv run --locked python scripts/youtube/discover_videos.py
uv run --locked python scripts/youtube/collect_comments.py
uv run --locked python scripts/youtube/collect_random_sample.py status
uv run --locked python scripts/youtube/prepare_screening.py --database data/youtube/work_sample_v2/sample.sqlite3 --output data/youtube/screening/work_v1
uv run --locked python scripts/youtube/run_screening.py --input-dir data/youtube/screening/work_v1 --output data/youtube/screening/work_v1/luna_predictions.jsonl --limit-batches 1
uv run --locked python scripts/classify_comments.py --limit 50
uv run --locked python scripts/run_web.py
```

Edit `config/youtube/approved_videos.json` to change approved video IDs and the comment
limit. IDs must already exist in the collected metadata. Select another file
with `--selection path/to/selection.json`. Completed samples are skipped;
changing the comment limit alone does not revisit them (`--refresh-comments` does).
Native classification needs a running Ollama with the model installed.
Use `make check` for offline tests or see the equivalent commands below.

## Other sources

```text
uv run --locked python scripts/jobs/collect_full.py --start 131000 --end 170000
uv run --locked python scripts/hn/collect_hiring.py
uv run --locked python scripts/wykop/collect_entries.py
uv run --locked python scripts/wykop/collect_comments.py
uv run --locked python scripts/wykop/classify_entries.py
```

Collectors append to their CSV and resume when rerun. `collect_full.py` writes KPRM ads in
the RepOD format (doi:10.18150/Q23MGT) to `data/jobs/`, next to the 2018-2023 release.
Hacker News uses only the official APIs; Wykop uses API v3 and stores `author_hash`
(salted SHA-256) instead of usernames. Wykop tags, start date and the comment rule are in
`config/wykop/collection.json`. `classify_entries.py` applies the YouTube instruction
and labels with a CLARIN-PL model. Credentials: `WYKOP_KEY`, `WYKOP_SECRET`, `WYKOP_SALT`,
`CLARIN_TOKEN`, `CLARIN_MODEL` in `.env`. The notebook in `notebooks/` reads the RepOD data.

## Documentation

- [Komentarze YouTube: przewodnik](docs/youtube/przewodnik-komentarze.md): cel H1,
  pobieranie, pliki, paczki dla małego modelu i dalsza analiza.
- [Operations](docs/operations.md): Makefile, Docker, GPU, CSV fields and resuming.
- [YouTube collector](docs/youtube/youtube-collector.md): collection behavior and privacy.
- [Sampling methodology](docs/youtube/comment-sampling.md): research limitations.
- [Seeded English sample](docs/youtube/random-sample.md): resumable work-topic searches,
  ChatGPT launch cutoff, language and engagement filters, Label Studio export.
- [H1 screening batches](docs/youtube/h1-screening.md): bounded comment JSONL for a small model.
- [YouTube labeling and validation](docs/youtube/comment-labeling-guide.md): codebook,
  blind pilot/evaluation sheets, human gold standard and model quality reports.
- [YouTube pilot results](docs/youtube/validation-results.md): completed 50-comment
  single-annotator validation, reproducible reports and methodological limitations.
- [KPRM job ads](docs/jobs/kprm-collection.md): pilot sample of public job advertisements.
- [Skill scope](docs/jobs/skill-scope.md): codebook and pre/post-2023 comparison.
- [ESCO skills](docs/jobs/esco.md): downloading the Polish ESCO skills taxonomy.
- [Labeling guide](docs/jobs/labeling-guide.md): gold standard (hand labels) for validating the codebook and ESCO mapping.
- [ESCO mapping](docs/jobs/esco-mapping.md): embedding match of fragments to ESCO and threshold calibration.
- [Candidate review](docs/youtube/youtube-candidates-review.md): rationale for the pilot list.

## Moving to another repository

Copy `amc/`, `scripts/`, `config/`, `docs/`, `tests/`, README, Makefile, Dockerfile,
Compose files, `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`,
`.gitignore`, `.dockerignore`, `.editorconfig` and `.gitattributes`.
Do not copy `.git`, `.venv`, caches or `.idea`. Create `.env` privately in the new
location. Copy all CSV files in `data/` separately if preserving collection and
classification history. Raw collections stay out of Git; the exceptions are listed in
[Versioned research data](docs/operations.md#versioned-research-data). Stop writers before copying.
A different directory name gives Compose a different project name and model
volume; the new project may download the model again. To intentionally reuse the
existing stack and volume, use `docker compose -p amc_projekt ...` and stop the
old stack first to avoid port conflicts. Otherwise keep projects isolated.

```text
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest discover -s tests
```

## Repository layout

- `amc/youtube/`: collection, CSV storage and reviewed video selection.
- `amc/classification/`: Ollama client and batch classification.
- `amc/jobs/`: KPRM job-advertisement sampling, parsing and CSV storage; full collection
  in the RepOD format (`repod.py`, `full.py`).
- `amc/hn/`, `amc/wykop/`: Hacker News and Wykop collection; Wykop classification uses
  `amc/classification/clarin.py`.
- `notebooks/`: exploratory analysis.
- `amc/esco/`: ESCO skills download for competence mapping.
- `amc/web/`: browser interface.
- `scripts/youtube/`: discovery and collection entry points.
- `config/youtube/`: reviewed video configuration.
- `data/youtube/`: raw CSV, classified CSV, progress and backups (not committed).
- `docs/youtube/`: collection and sampling documentation.

`python -m amc` remains a compatibility entry point; `python -m amc.youtube` is
also supported. The collection default directory is now `data/youtube`.
Job-advertisement data goes to `data/jobs/`, Hacker News to `data/hn/` and Wykop to
`data/wykop/` (not committed).
