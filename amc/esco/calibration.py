"""Choose a similarity threshold from hand-reviewed top-1 proposals."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ThresholdRow:
    threshold: float
    accepted: int
    precision: float
    recall: float
    f1: float


def threshold_table(scores: list[float], correct: list[bool]) -> list[ThresholdRow]:
    """Precision, recall and F1 of accepting a top-1 proposal when score >= threshold.

    Recall is relative to the proposals reviewed as correct; fragments with no true ESCO
    counterpart can only lower precision, never recall.
    """
    if len(scores) != len(correct) or not scores:
        raise ValueError("Scores and verdicts must be non-empty and of equal length.")
    total_correct = sum(correct)
    rows = []
    for threshold in sorted(set(scores)):
        accepted = [ok for score, ok in zip(scores, correct, strict=True) if score >= threshold]
        hits = sum(accepted)
        precision = hits / len(accepted)
        recall = hits / total_correct if total_correct else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        rows.append(ThresholdRow(threshold, len(accepted), precision, recall, f1))
    return rows


def best_threshold(rows: list[ThresholdRow], min_precision: float = 0.0) -> ThresholdRow:
    """Highest-F1 row among those meeting `min_precision`; ties go to the higher threshold."""
    eligible = [row for row in rows if row.precision >= min_precision] or rows
    return max(eligible, key=lambda row: (row.f1, row.threshold))
