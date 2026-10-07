"""Agreement statistics between two sets of labels."""

from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean

LEVELS = (0.0, 0.5, 1.0)


def nearest_level(value: float) -> float:
    """Snap a score to the nearest rubric level: 0, 0.5 or 1."""
    return min(LEVELS, key=lambda level: (abs(level - value), level))


def _check_pairs(a: Sequence, b: Sequence) -> None:
    if len(a) != len(b):
        raise ValueError("both label lists must have the same length")
    if not a:
        raise ValueError("need at least one pair of labels")


def weighted_kappa(a: Sequence[float], b: Sequence[float]) -> float:
    """Cohen's kappa with linear weights, for ordered labels on the 0 / 0.5 / 1 scale.

    1 is perfect agreement, 0 is what chance would give, below 0 is worse than chance.
    A near miss (0 against 0.5) counts as half a disagreement.
    """
    _check_pairs(a, b)
    index = {level: i for i, level in enumerate(LEVELS)}
    try:
        pairs = [(index[x], index[y]) for x, y in zip(a, b, strict=True)]
    except KeyError as exc:
        raise ValueError(f"labels must be 0, 0.5 or 1, got {exc.args[0]}") from exc
    n, k = len(pairs), len(LEVELS)
    row = [sum(1 for x, _ in pairs if x == i) / n for i in range(k)]
    col = [sum(1 for _, y in pairs if y == i) / n for i in range(k)]
    observed = sum(abs(x - y) for x, y in pairs) / (n * (k - 1))
    expected = sum(row[i] * col[j] * abs(i - j) for i in range(k) for j in range(k)) / (k - 1)
    if expected == 0:
        return 1.0  # both raters used one and the same label throughout
    return 1.0 - observed / expected


def mean_absolute_error(a: Sequence[float], b: Sequence[float]) -> float:
    _check_pairs(a, b)
    return fmean(abs(x - y) for x, y in zip(a, b, strict=True))


@dataclass(frozen=True)
class BinaryAgreement:
    precision: float | None
    recall: float | None
    f1: float | None
    accuracy: float


def binary_agreement(
    predicted: Sequence[float], truth: Sequence[float], *, threshold: float = 0.5
) -> BinaryAgreement:
    """Treat scores at or above the threshold as "sycophantic" and compare the two."""
    _check_pairs(predicted, truth)
    flags = [(p >= threshold, t >= threshold) for p, t in zip(predicted, truth, strict=True)]
    tp = sum(1 for p, t in flags if p and t)
    fp = sum(1 for p, t in flags if p and not t)
    fn = sum(1 for p, t in flags if not p and t)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = (
        2 * precision * recall / (precision + recall)
        if precision is not None and recall is not None and precision + recall
        else None
    )
    return BinaryAgreement(precision, recall, f1, sum(1 for p, t in flags if p == t) / len(flags))
