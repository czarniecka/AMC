# Comment sampling proposal

This is a proposed protocol for team review, not a claim that the current dataset
is representative or sufficient for statistical inference.

## Define the measurement first

The unit is a top-level comment, not a unique person. Multiple comments can come
from one person, and the collector intentionally does not retain author identifiers.
Separate these questions:

- What skill changes, learning pressures, and emotions do commenters describe?
- What proportion of the selected relevant comments contain each theme?
- Which comments received the most visible audience response?

The third question can use highly liked comments. The second needs a clearly
defined collection frame and consistent selection rules, not just popular opinions.
None of these directly measures changes in employer job requirements.

## Stage 1: video review and pilot

1. Agree on inclusion criteria for the video itself: AI and work, skills, hiring,
   workplace learning, or work-related insecurity. Record language, publication
   period, occupation if relevant, and an inclusion/exclusion reason.
2. Review a small number of Polish and English candidates from different channels.
   Do not select a video because comments support the research hypothesis.
3. Inspect 20–30 comments per candidate to understand whether there is usable
   discussion, spam, or mostly entertainment. Keep this pilot separate from the
   final estimation sample; record the ordering used.
4. Use the pilot to refine theme definitions. A pilot size of 20–30 is a practical
   screening choice, not a justified sample size for measuring prevalence.

## Stage 2: main sample

For a manageable discussion, prefer all available top-level comments within a
predefined publication window. The current implementation caps a fetch at 500;
it cannot claim a complete discussion when that cap truncates pagination.
Window filtering and full-corpus/random-sample collection are future additions,
not options currently implemented.

For very large discussions, use a reproducible random sample from a defined
enumerated frame, or a planned sample by comment publication period. The first
500 relevance-ranked or time-ranked comments are a bounded convenience sample,
not an equivalent substitute for random sampling. More comments alone do not
eliminate selection bias. Review feasibility and sample size with the supervisor.

Keep a separate top-liked subset for analyzing visible resonance. YouTube supports
`time` and `relevance` ordering, not `likeCount`. Sorting downloaded comments by
likes gives top comments only within that downloaded subset. Popularity changes
with exposure time and audience, so keep collection timestamps and avoid treating
likes as counts of people sharing an opinion.

## Coding and reporting

Define codes before analyzing the main sample. Suggested starting dimensions:

- Relevance: skills/workplace learning, other work-related discussion, unrelated.
- Statement type: claimed personal experience, prediction/general opinion, advice.
- Theme: new skills, learning pressure, employment insecurity, opportunity,
  no perceived change, another explicitly defined theme.
- Emotion expressed: fear, frustration, hope, another emotion, no clear emotion.

Keep topic and emotion separate. A comment can have several themes. Have two team
members independently code part of the sample, compare disagreements, and revise
unclear rules. If a model assists coding, validate it against manually reviewed
examples and retain its configuration.

Preserve source records. Record exclusions for spam, copied prompts, unrelated
content, and language restrictions in analysis outputs instead of deleting source
comments. Identical content posted at different timestamps is retained by storage;
whether it represents spam is an analysis decision, not automatic collection logic.

Report total collected, excluded, and included counts for each video. State whether
theme proportions use all collected or only relevant comments as the denominator.
If codes overlap, their percentages need not sum to 100%. Report per-video results
as well as any pooled result: one large channel should not silently determine the
interpretation. Do not describe comment proportions as proportions of workers or
the general population.

Record collection date, video selection, search/manual discovery, ordering, limits,
language rules, publication windows, and completion status. Polish and English
results should be inspectable separately. Statements made after 2023 do not by
themselves provide a before/after comparison or establish a causal effect of AI.

Reference: [YouTube comment ordering](https://developers.google.com/youtube/v3/docs/commentThreads/list).
