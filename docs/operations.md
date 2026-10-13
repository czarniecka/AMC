# AMC Project

Python tools for discovering YouTube videos, collecting comments and testing
local classification with Ollama. Code, comments and documentation use English.
Source titles, search phrases and collected text retain their original language.

## Setup

Install uv and run `uv sync --locked`. Copy `.env.example` to `.env` and enter
your YouTube API key locally. Existing environment variables take precedence.
Never commit or share `.env`; Git and Docker builds exclude it.

```text
uv run --locked python -m amc --help
uv run --locked python -m amc --discover-only --candidates-per-query 100
uv run --locked python -m amc --video-id h0hdaHPKDdI --max-comments 100
```

Repeat `--video-id` for multiple approved films. IDs must exist in the selected
output CSV history. This mode makes no searches. See [collector details](docs/youtube/youtube-collector.md),
[candidate review](docs/youtube/youtube-candidates-review.md) and [sampling guidance](docs/youtube/comment-sampling.md).

## Remote server and Docker

Prepare `.env` privately on the server. Transfer `data/` separately to retain
history, including `yt_collection_state.csv`. Keep backups and run only one collector
per output directory. 

```sh
docker build -t amc .
docker run --rm amc
docker run --rm --env-file .env -v "$(pwd)/data:/app/data" amc --video-id h0hdaHPKDdI --max-comments 100
```

The image contains runtime dependencies and application code only. Secrets are
supplied at runtime with `--env-file`, not copied into the image. The collector
is a batch program, not a continuously running service. Use plain `NAME=value`
entries without quotes in `.env` for compatibility with Docker's environment parser.


## Browser app, Python scripts and Makefile

```text
make setup
make discover
make collect
make web
```

`discover` finds metadata only. `collect` downloads up to 100 comments from the
approved cached videos configured in `config/youtube/approved_videos.json`, without searches or transcripts. Pass extra options
with `make collect ARGS="--max-comments 30"`. Keep `.env` private.

If Make is unavailable (common on Windows), use the same Python entry points:

```text
uv run --locked python scripts/youtube/discover_videos.py
uv run --locked python scripts/youtube/collect_comments.py
uv run --locked python scripts/run_web.py
```

The browser app is available at http://localhost:8501. Paste a comment and click
Classify for relevance and impact. Predictions are not automatically saved and
require human review. 
For a local Python launch, Ollama must run separately with the model installed.
Configure `OLLAMA_BASE_URL` and `OLLAMA_MODEL` in `.env` when needed.

## Containerized Ollama and web app

```text
make up
make logs
make docker-discover
make docker-collect
make down
```

Without Make, start the app with `docker compose up --build -d web`.
Compose uses a separate official Ollama container and a one-shot initialization
container that downloads `OLLAMA_MODEL` (default `qwen3:8b`) before starting the
web app. Model files persist in `ollama-models`. Initial downloads can take time
and require several GB of disk space. `docker compose down` retains models;
do not use `down -v` unless deliberately discarding them.

The container web app is published on http://localhost:18501 by default.
Set `WEB_PORT` in `.env` to change the host port; the Python-only app uses 8501. Ollama is reachable
inside the Compose network and is not published on the host. The web container
receives no YouTube key. The collection service reads `.env` at runtime and mounts
`data/` to preserve results. Do not expose the web app directly on a remote public
server; use an SSH tunnel for private access. The app has no authentication.

The default is CPU inference. NVIDIA GPU deployment requires the NVIDIA Container
Toolkit and a GPU reservation in Compose. Follow the official Ollama Docker guide:
https://docs.ollama.com/docker . Native host Ollama and container Ollama have
separate model stores; a model downloaded on Windows is not automatically in Docker.

## Local checks

```text
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest discover -s tests -v
```

Tests use simulated responses and do not consume YouTube quota. Manage dependencies
with uv and keep `pyproject.toml` and `uv.lock` together. Credentials, generated
data and personal IDE settings stay local.

## CSV data contract

The authoritative files in `data/` are UTF-8 with BOM, comma-delimited, with headers:

| File | Fields |
| --- | --- |
| `yt_videos_metadata.csv` | video_id, title, channel_title, published_at, view_count, comment_count |
| `yt_comments_anonymized.csv` | video_id, comment_id, text_clean, like_count, published_at |
| `yt_transcripts.csv` | video_id, transcript |
| `yt_collection_state.csv` | video_id, completed, sample_limit, comment_order |

`comment_id` is a persistent generated UUID. Original author and comment identifiers
are not stored. Duplicate detection uses video ID, text and publication timestamp.
Empty cells represent missing values; timestamps remain ISO 8601 strings from API.
`completed` is 0 or 1 and means the bounded sample finished, not every source comment.
Store all four files together. Each updated file is replaced atomically; updates
across files are not a single transaction. A lock prevents simultaneous writers.
After a process crash, remove `data/.collection.lock` only once no collector runs.
CSV persistence rewrites a file when adding records, so large collections can be
slower than database storage. Keep raw collection files unchanged during analysis;
use copies or separate files for labels and manual edits.

On first use after upgrading, an existing SQLite history is read once, backed up,
and migrated to CSV with completion flags preserved. The database is retired into
`data/backups/`; normal runs no longer use it. Older CSV-only collections without
state mark videos with stored comments as completed samples conservatively.
Spreadsheet formula-like text is escaped with an apostrophe for safe display.
The reader decodes that prefix when restoring records. Preserve this convention.
## Automatic comment classification

```text
make classify ARGS="--limit 50"
uv run --locked python scripts/classify_comments.py --limit 50
make docker-classify ARGS="--limit 50"
```

Omit `--limit` to process all pending comments. The native command needs a running
Ollama service with the selected model installed. The Compose command starts
Ollama and model initialization automatically. No YouTube key is required.

Results are stored separately in `data/youtube/yt_comments_classified.csv` with columns:
`video_id`, `comment_id`, `text_hash`, `relevance`, `impact`, `model`, `prompt_hash`,
`classified_at`. Join with source comments by `video_id` and `comment_id`.
Classification has two stages: relevance to AI and work/skills, then perceived
positive, negative, mixed, neutral or unclear impact. Unrelated comments have
unclear impact. No evidence text or probability is requested.

Each prediction is saved atomically immediately. Reruns skip matching comment ID,
text hash, model tag and prompt hash. Changing text, model tag or instructions
creates a new prediction while retaining older rows. Model tags are not immutable;
record the installed model digest separately if upgrading weights under one tag.
On failures or interruption, rerun to resume. A lock prevents concurrent writers;
after a crash remove the output `.csv.lock` only after confirming no run is active.
The source comments are never modified. The output starts with headers only and
remains excluded from Git. Validate predictions manually before research analysis.

## Optional NVIDIA GPU

The default Compose setup remains CPU-only. Enable NVIDIA GPU support explicitly:

```text
make up GPU=1
make docker-classify GPU=1 ARGS="--limit 100 --seed 20261013"
```

Without Make:

```text
docker compose -f compose.yaml -f compose.gpu.yaml up -d web
docker compose -f compose.yaml -f compose.gpu.yaml run --rm classifier scripts/classify_comments.py --limit 100 --seed 20261013
```

Use the same GPU override on subsequent Compose commands to avoid recreating
Ollama in CPU mode. Return to CPU with `docker compose up -d ollama`.
`--seed` shuffles the comments reproducibly before skipping completed predictions.
The classifier reports total wall time and mean time per newly classified comment.
Duration estimates depend on comment length, GPU load, model loading and CSV size.
GPU container support requires compatible NVIDIA drivers and Docker configuration:
https://docs.docker.com/compose/how-tos/gpu-support/ .


Select another approved list with --selection path/to/selection.json. Rebuild the container after changing bundled configuration.
