# GPU pilot benchmark ? 2026-10-13

- Model: qwen3:8b, installed digest 500a1f067a9f, Ollama 0.40.2.
- Hardware: NVIDIA RTX 4060 8 GB; Ollama reported 100% GPU.
- Input: 1,628 stored comments. Reproducible shuffle seed: 20261013.
- Saved: 100 predictions covering 20 videos in data/youtube/yt_comments_classified.csv.
- Full batch wall time: 197.4 seconds, including first model load/request.
- Time between first and last saved prediction: 54.39 seconds for 99 subsequent
  comments, averaging 0.549 seconds per comment (including CSV persistence).
- Remaining: 1,528 comments. Linear warm-model estimate: 839 seconds, about 14 minutes.
  Allow 15?20 minutes with startup overhead and workload variation. Extrapolating
  the full cold-batch mean gives about 50 minutes, an intentionally conservative
  calculation that repeats startup overhead which normally occurs only once.
- Model predictions: 61 relevant, 39 unrelated. Impact labels: 25 mixed,
  41 unclear, 19 negative, 7 neutral, 8 positive. These counts are predictions,
  not human-validated accuracy or population estimates.

Status of validation: there is no codebook file and no hand-labeled gold standard for
YouTube comments yet, so accuracy of the model is unknown. Planned: write the codebook,
hand-label a random sample (ideally by two coders, with kappa), then compare model labels
with it before classifying the rest. See [sampling](youtube/comment-sampling.md).

The run was capped at 100. Source comments were not modified. To continue:
`make docker-classify GPU=1` (no limit). Already saved predictions are skipped.
