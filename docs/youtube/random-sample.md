# English YouTube comment sample

This is a separate collection from the reviewed AI-video pilot. The default
sampling frame is videos returned by seeded English searches about the future of
jobs and automation, AI-exposed IT jobs and general job search, **not** all YouTube
videos. The versioned [work query list](../../config/youtube/work_queries.txt)
contains no explicit AI or ChatGPT terms; how the phrases were chosen and their
limits are in [query selection](query-selection.md). This topic-enriched sample cannot
estimate AI discussion across all YouTube comments.
Video publication periods are `pre_chatgpt` (2019-01-01 through 2022-11-29)
and `post_chatgpt` (2022-11-30 through 2026-12-31). The date boundary is the
public launch date of ChatGPT
([OpenAI announcement](https://openai.com/index/chatgpt/)); the API's publication
timestamps are compared in UTC. With a date-only announcement, the entire UTC day
of November 30 is assigned to `post_chatgpt`.
Each eligible video must have
at least 10,000 views, an English `defaultAudioLanguage` or `defaultLanguage` in API
metadata, and at least 50 comments (`--min-comments`, default 50). Only top-level comments with at least 20
characters after text cleaning are stored, regardless of likes. Their text must
also pass `langdetect` with English probability at
least 0.90. This is an imperfect automated language screen, especially for short
texts. Check a human sample of both included and excluded comments. The database
counts comments rejected by length and by language for each video, without retaining
their texts. Searches are partitioned by the **video's** publication date, while
the equal minimum quotas are counted by `comment_period`, computed from the
**comment's** publication date. Both periods are exported to Label Studio. A 2024
comment on a 2021 video is post-launch commentary.

## Commands

```text
uv run --locked python scripts/youtube/collect_random_sample.py collect --target 50000 --seed 20261025
uv run --locked python scripts/youtube/collect_random_sample.py status
uv run --locked python scripts/youtube/collect_random_sample.py export --export-count 500 --seed 20261025 --output data/youtube/work_sample_v3/label_studio_v1
```

The same database resumes after interruption or after increasing `--target`. Other
sampling settings and the SHA-256 of the vocabulary file are frozen on the first
run; changing them requires a new database. The default database is
`data/youtube/work_sample_v3/sample.sqlite3`, using the revised work queries and
minimum 50 comments per video. The older `work_sample_v2` database uses a
different query list and protocol; keep it separate and do not resume it with
current defaults. The previous broad sample remains
at `data/youtube/random_sample/sample.sqlite3`. The first work sample, if
collected, remains at `data/youtube/work_sample/sample.sqlite3`. Those databases
used different filters and must not be mixed. Search visits each query/quarter
pair once in a seeded order. A custom list of words or phrases can be passed
with `--words` before the first run. Search queries and
within-query video order derive independently from the base seed and query index.
`searches`, `videos`, and `comments` in `sample.sqlite3` record the actual API
outcomes. A seed alone cannot reproduce a changing external search index.

`--target` controls how many eligible comments are stored (split approximately
equally by comment date across periods). `--export-count` controls how many are
sent to Label Studio. Export is deterministic for the same frozen database,
`--export-count`, and `--seed`: it takes exactly half from each period for an
even count (for an odd count, one extra from `pre_chatgpt`). If a period has
too few comments, export fails rather than filling from the other period. It
alternates periods and cycles through videos in seeded order, then draws
comments in seeded order within each video. This
spreads annotations across videos; it is not a uniform random sample of comments.
Omit `--export-count` to export everything. Requesting more comments than stored
is an error. A later collection run changes the pool and can change the selected
subset, so keep each exported snapshot.

Each request asks for the largest API page: 50 search results or 100 comment
threads. One completed comment page and its next-page token are committed in one
SQLite transaction; reruns continue from the saved token. The API may change
between runs, so a crash between receipt of an API response and its database
commit can still change that one page. The collector uses `order=time` and
paginates a video until exhausted or the period's target is met. Raising the target
continues from that point. It stops at the first completed page after each period's
minimum quota, so counts may exceed the exact target by up to one page per period.
If a video has no English language metadata, it is excluded. This conservative
rule can greatly reduce yield; review the number of searches and accepted videos.

The local request budget defaults to 80 per run (`--max-api-requests`). A budget or
API quota stop leaves committed work intact. YouTube's search endpoint has its own
quota; even with a larger local budget, repeated runs may need to wait for the
YouTube quota reset. Do not run two collectors against one database. If a process
crashes, remove `sample.sqlite3.lock` only after verifying no writer remains.

## Label Studio

Label Studio is a separate application; it is not installed by this project's
`uv` environment. To run it locally with Docker, from the repository root:

```bash
mkdir -p data/label_studio
docker run --rm --user "$(id -u):0" -p 8080:8080 -v "$PWD/data/label_studio:/label-studio/data" heartexlabs/label-studio:latest
```

Open `http://localhost:8080`, create a local account, then **Create Project**.
Name it, open **Labeling Setup**, choose **Code**, and paste the complete contents
of `config/youtube/label_studio.xml`. Save the project. In **Data Import**, upload
`data/youtube/work_sample_v3/label_studio_v1/tasks_0000.json` (or the `tasks_*.json`
files in whichever directory you exported). Then open a task and label it.
The JSON key `data.text` matches the XML's `$text` field. Keep the
`data/label_studio` directory: it contains Label Studio's account, project, and
annotations. This is distinct from the collector's `sample.sqlite3`.

To export the current collector database before import, run:

```bash
uv run --locked python scripts/youtube/collect_random_sample.py export --export-count 500 --seed 20261025 --output data/youtube/work_sample_v3/label_studio_v2
```

The output directory must be new or empty. Import only one snapshot into a given
Label Studio project; exporting again after collection repeats earlier tasks. For
additional comments, create a new export and avoid importing duplicate IDs.

Use [label_studio.xml](../../config/youtube/label_studio.xml) as the project labeling
configuration. Import each `tasks_*.json` from the export directory as JSON tasks.
The files contain one `data.text` per comment, stable `data.comment_id` and
`data.video_id`, `video_period`, `comment_period`, dates, likes, views, video title,
and search query. Import an export only
once into a Label Studio project: rerunning export to a new directory repeats all
tasks. Keep the local SQLite database as the source of truth and retain the Label
Studio annotation export separately. The XML shows the search query and video
title so annotators can audit video selection. They are context, not proof that
the comment itself discusses AI or work; label those fields from comment text.
The publication period remains hidden in the labeling view.

The two always-visible questions are `ai_related` and `work_related`. If both are
`No`, all other fields remain absent from the annotation. `ai_attitude` appears
only for AI-related comments; `work_attitude` appears only when both AI and work
are related. The remaining detailed fields, including `sector`, appear only for
work-related comments. Hidden fields are missing values, not `Neutral` or
`Unspecified` labels. `Unclear` in a gate does not open detailed fields; review
these cases separately.

The `sector` field is labeled for **every work-related comment**, independently of AI relevance.
It uses the seven values supplied in the Wykop stage-2 guide: `it` (software and
systems), `creative` (design, writing, translation, music, film), `office`
(administration and accounting), `service` (customer service and sales),
`education` (teaching and research), `other` (another explicitly named occupation
or industry), and `unspecified` (no occupation or industry named). Choose the
sector of the comment's main point if several are mentioned. Use only the
comment's text; a video about IT does not make a generic comment an IT comment.
This differs from `topics=Education`: a worker discussing retraining has an
education *topic* but may work in another sector.

## Interpretation

The equal quotas balance numbers of **eligible comments grouped by comment date**, not films.
Highly
commented videos can dominate collection, although the capped export rotates
between videos. The 20-character filter removes short reactions but may also
exclude concise meaningful comments.
Use video-clustered uncertainty intervals, report each period's eligible video
and comment counts, and inspect comment dates. Work-related search phrases and an
English video and comment language filters do not make a representative sample of
English YouTube comments. Freeze a human-labeled evaluation set before fitting any
classifier.
