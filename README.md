# AMC YouTube collector

Collect YouTube video metadata and top-level comments into cumulative CSV files.
No author metadata is requested. Captions are optional. Comment text may still
contain identifying information and needs review before sharing.

## Setup

Install uv, then run `uv sync --locked` from the repository root.
Copy `.env.example` to `.env` and enter `YOUTUBE_API_KEY` privately.
Existing environment variables take precedence. Do not commit `.env` or `data/`.

## Collect

```text
uv run --locked python scripts/youtube/discover_videos.py
uv run --locked python scripts/youtube/collect_comments.py
uv run --locked python -m amc.youtube --help
```

Edit `config/youtube/approved_videos.json` to select video IDs and a comment limit.
Use `--selection path/to/selection.json` for another list. Missing video metadata
is fetched directly by ID; approved-list collection makes no search requests.
The default publication cutoff is January 1, 2023. Unavailable or older selected
videos stop the run with completed records preserved.

## Data

Keep the four CSV files in `data/youtube/` together: video metadata, comments,
transcripts and collection state. Files use UTF-8 BOM encoding. New results are
merged with existing records; completed bounded samples are skipped. Use
`--refresh-comments` to revisit them. Duplicate detection uses video ID, cleaned
text and publication time. Each file is replaced atomically, not the entire set.
Invalid headers and missing files for recorded progress stop loading without
replacing the collection. Run only one collector per output directory. After a
crash, remove `.collection.lock` only when no collector is running. Keep backups.

## Offline checks

```text
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest discover -s tests
```

Tests use simulated responses, not live API requests. The lockfile also includes
Streamlit for subsequent analysis functionality; Ollama and models are not
installed by uv. Local IDE configuration is excluded from version control.
