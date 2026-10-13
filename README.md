# AMC Project

YouTube comment collection and local classification with Ollama/Qwen.
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
uv run --locked python scripts/classify_comments.py --limit 50
uv run --locked python scripts/run_web.py
```

Edit `config/youtube/approved_videos.json` to change approved video IDs and the comment
limit. IDs must already exist in the collected metadata. Select another file
with `--selection path/to/selection.json`. Completed samples are skipped;
changing the comment limit alone does not revisit them (`--refresh-comments` does).
Native classification needs a running Ollama with the model installed.
Use `make check` for offline tests or see the equivalent commands below.

## Documentation

- [Operations](docs/operations.md): Makefile, Docker, GPU, CSV fields and resuming.
- [YouTube collector](docs/youtube/youtube-collector.md): collection behavior and privacy.
- [Sampling methodology](docs/youtube/comment-sampling.md): research limitations.
- [Candidate review](docs/youtube/youtube-candidates-review.md): rationale for the pilot list.

## Moving to another repository

Copy `amc/`, `scripts/`, `config/`, `docs/`, `tests/`, README, Makefile, Dockerfile,
Compose files, `pyproject.toml`, `uv.lock`, `.python-version`, `.env.example`,
`.gitignore`, `.dockerignore`, `.editorconfig` and `.gitattributes`.
Do not copy `.git`, `.venv`, caches or `.idea`. Create `.env` privately in the new
location. Copy all CSV files in `data/` separately if preserving collection and
classification history, and keep them out of Git. Stop writers before copying.
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
- `amc/web/`: browser interface.
- `scripts/youtube/`: discovery and collection entry points.
- `config/youtube/`: reviewed video configuration.
- `data/youtube/`: raw CSV, classified CSV, progress and backups (not committed).
- `docs/youtube/`: collection and sampling documentation.

`python -m amc` remains a compatibility entry point; `python -m amc.youtube` is
also supported. The collection default directory is now `data/youtube`.
No folders for future job-offer data have been created.