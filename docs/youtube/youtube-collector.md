# YouTube collector

## Setup and first run

Enable YouTube Data API v3 in your Google Cloud project and create an API key.
The collector loads the root `.env` without overriding existing environment variables.
It reads `YOUTUBE_API_KEY` and does not require OAuth. Restrict the key to the API
and the intended environment using the provider's key settings.

Copy `.env.example` to `.env` and enter your key locally, then run:

```text
uv sync --locked
uv run --locked python -m amc --max-videos 5 --max-comments 100
```

Never share `.env`. The program does not print the key, response bodies,
or HTTP request URLs. The default run searches six phrases (three Polish and three
English), examines up to 50 candidates per phrase, selects up to 20 videos, and
collects up to 500 top-level comments per selected video.

Captions are optional and disabled by default:

```text
uv run --locked python -m amc --with-transcripts
```

Use custom phrases by repeating the language-specific options. Providing any
custom phrase replaces all default phrases:

```text
uv run --locked python -m amc --query-pl "sztuczna inteligencja rynek pracy" --query-en "AI job market skills" --max-videos 10
```

Other options include `--published-after`, `--candidates-per-query` (1–500),
`--max-videos` (1–500), `--max-comments` (0–500), `--max-api-requests`, and
`--output-dir`. `--comment-order time` selects API chronological ordering instead
of relevance; neither is random sampling or a global ranking by likes.
`--refresh-comments` explicitly revisits completed samples, for example after
increasing the limit or deliberately changing the ordering. Without that flag,
a completed sample is skipped even if the configured limit changes.
Run `uv run --locked python -m amc --help` for the complete interface.

## Discover candidates and collect approved videos

```text
uv run --locked python -m amc --discover-only --candidates-per-query 250
uv run --locked python -m amc --video-id h0hdaHPKDdI --max-comments 100
```

Discovery stores candidate metadata without comments or captions. Review topical
relevance and language before collecting. Repeat `--query-pl` or `--query-en` to
customize search phrases. Stored results are preserved after a handled API stop.

Repeat `--video-id` to collect only approved cached videos without searching.
Every selected ID must exist in the output CSV history, and `--max-videos` must cover
the list. Completed samples are skipped unless `--refresh-comments` is supplied.
The sample is exploratory, not random or representative. Credentials come from
`.env` or existing environment variables; no PowerShell helper scripts are needed.

## Modules

| Module | Responsibility |
| --- | --- |
| `api_client.py` | Environment key, HTTP timeouts, request budget, safe errors |
| `video_finder.py` | Bilingual search, pagination, deduplication, statistics, ranking |
| `comment_extractor.py` | Top-level comments, pagination, field allowlist, UUIDv4 |
| `transcript_fetcher.py` | Optional captions, pl/en preference, spacing and missing captions |
| `exporter.py` | Allowlisted CSV columns, UTF-8 BOM, individual atomic file replacement |
| `collector.py` | Configuration, orchestration, partial-output recovery |
| `models.py` | Typed records and default search phrases |
| `storage.py` | Authoritative CSV history, one-time migration, duplicate detection |
| `__main__.py` | Command-line interface and exit codes |

`find_videos` returns a metadata table as a list of typed `VideoMetadata` records.
`YouTubeDataCollector.collect()` returns a `CollectionResult` with videos, comments,
transcripts, and `stopped_reason`, while also writing CSV exports.

## Search and sampling

The default cutoff is `2023-01-01T00:00:00Z`. Search uses `publishedAfter`; metadata
is checked again to exclude records at or before the cutoff.

YouTube `search.list` does **not** support `order=commentCount`. The implementation
uses `order=relevance`, retrieves video statistics, and ranks the deduplicated
candidate pool locally by descending `comment_count`. Increasing
`--candidates-per-query` broadens the pool at the cost of more requests. This is
not a global ranking of every matching YouTube video.

`relevanceLanguage=pl/en` is a relevance hint, not a strict language guarantee.
Both languages are searched by default, but ranking does not force equal language
representation. Inspect results for topical relevance and actual language.
Missing view/comment statistics remain `None`, exported as empty cells. Videos
with unknown comment counts sort last.

Comments are top-level only; replies are neither requested nor exported.
`order=relevance` selects relevant comments, not a random or representative sample,
and does not guarantee descending likes. New records receive UUIDv4 identifiers;
saved records keep their original UUID on subsequent runs. A separate internal
SHA-256 fingerprint of video ID, cleaned text, and publication timestamp detects
duplicates across runs without source comment or author identifiers. Distinct
comments with exactly the same text and timestamp on one video can be merged;
an edited source comment can appear as a new record. Likes do not affect matching.

## Privacy scope

The comment endpoint uses this server-side `fields` allowlist:

```text
nextPageToken,items(snippet/topLevelComment/snippet(textDisplay,likeCount,publishedAt))
```

It requests no author names, channel identifiers, channel links, avatars, original
comment identifiers, or replies. The only stored comment identifier is UUIDv4.
API plain-text output is decoded and whitespace-normalized. Raw responses and
comment text are not logged.

The requested filename `yt_comments_anonymized.csv` describes the removal of author
metadata; it does not establish complete anonymization or GDPR compliance. Free
text may itself contain names or identifying details, and text can be searchable
on the source platform. Review or redact free text before sharing it.
Video channel titles are retained because they are an explicitly required field
of the separate video metadata export.

## Caption behavior

The installed `youtube-transcript-api` uses `YouTubeTranscriptApi().fetch` with
`languages=["pl", "en"]`. Snippet text is joined into one whitespace-normalized
string. `TranscriptsDisabled` and `NoTranscriptFound` produce `None` and allow
collection to continue. Other unavailable-caption conditions also produce `None`;
HTTP failures and blocking conditions stop collection.

The fetcher waits `random.uniform(0.5, 1.5)` seconds between consecutive video
caption fetches. Each fetch may internally perform multiple HTTP requests.
The owned HTTP session enforces timeouts and intercepts HTTP 403/429 before the
library wraps them. Spacing cannot guarantee that YouTube will allow requests;
the implementation stops on blocking and does not rotate proxies or identities.

## Exports and recovery

All three exports use `utf-8-sig`, have column headers even with no records, and
are excluded from Git. CSV empty cells represent `None`.

| File | Columns |
| --- | --- |
| `data/youtube/yt_videos_metadata.csv` | `video_id`, `title`, `channel_title`, `published_at`, `view_count`, `comment_count` |
| `data/youtube/yt_comments_anonymized.csv` | `video_id`, `comment_id`, `text_clean`, `like_count`, `published_at` |
| `data/youtube/yt_transcripts.csv` | `video_id`, `transcript` |

The transcript export has one row per selected video. A blank transcript means
unavailable, disabled, not requested, or not reached before an interruption.
Formula-like free-text cells beginning with `=`, `+`, `-`, or `@` are prefixed with
an apostrophe for spreadsheet safety; in-memory records retain their original text.

HTTP 403 or 429 stops further collection immediately and prints a safe message.
Not every 403 is quota-related: disabled comments and access problems can also
produce 403. In accordance with the stop policy, those errors also stop the run.
Temporary HTTP 5xx responses get at most two retries with bounded backoff.
Connection errors are reported without raw request details.

The default local budget is 200 Data API HTTP attempts, including retries. It is
not a measurement of Google's quota units or remaining account quota. Caption
requests use a separate interface and are not included in this counter.

Completed comment pages and completed video metadata are exported after a handled
API stop. If discovery stops early, ranking applies to only the metadata obtained
so far, and no further comment requests are made.
Each new comment is saved to the authoritative comment CSV immediately. Keep all
four CSV files together, including `yt_collection_state.csv`, which tracks completed
bounded samples. Interrupted samples retry pagination; stored duplicates retain
their UUID and first observed like count. Metadata retains its first observation.
Missing transcripts do not erase existing captions. Updates are atomic per file,
not across the entire dataset. A lock prevents simultaneous writers in one directory.

Existing SQLite history is backed up and migrated once, including completion flags,
then retired under `data/backups/`. Normal collection uses CSV only. Existing CSV
collections without state are backed up and conservatively mark videos containing
comments as completed. See the README CSV contract for columns and conventions.

Exit codes: `0` completed, `1` interrupted by an API or budget error with partial
exports, `2` configuration or file-system error, `130` user interruption.
For research reproducibility, record the commit, collection time, options, and
completion status along with each run. The collector does not infer causal changes
or treat this selected sample as representative of the labor market.
See [Comment sampling](comment-sampling.md) before choosing a collection strategy.

## Offline validation

```text
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked python -m unittest discover -s tests -v
```

Tests simulate API responses and require no YouTube credentials. They exercise
pagination, author-field exclusion, limits, UUIDs, BOM encoding, local sorting,
caption fallbacks, blocking, and partial-output recovery. A real collection still
requires a working key and network access.

## References

- [YouTube search parameters](https://developers.google.com/youtube/v3/docs/search/list)
- [YouTube video statistics](https://developers.google.com/youtube/v3/docs/videos/list)
- [YouTube comment threads](https://developers.google.com/youtube/v3/docs/commentThreads/list)
- [Partial responses](https://developers.google.com/youtube/v3/getting-started#partial)
- [YouTube API errors](https://developers.google.com/youtube/v3/docs/errors)
- [youtube-transcript-api](https://github.com/jdepoix/youtube-transcript-api)
