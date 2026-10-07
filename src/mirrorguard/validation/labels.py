"""Labelling sheets for human raters, and the comparison with the judge."""

import csv
import random
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mirrorguard.benchmark.judge import format_transcript
from mirrorguard.benchmark.repository import ScoredConversation
from mirrorguard.schemas import Rubric
from mirrorguard.validation.agreement import (
    BinaryAgreement,
    binary_agreement,
    mean_absolute_error,
    nearest_level,
    weighted_kappa,
)

FIXED_COLUMNS = ["conversation_id", "scenario_id", "user_summary", "transcript"]
Labels = dict[str, dict[str, float]]  # conversation id -> measure id -> label


def label_columns(rubric: Rubric) -> list[str]:
    """Measures a person labels. Computed measures are left out."""
    return [m.id for m in rubric.measures if m.method == "judge"]


def write_sheet(
    path: Path,
    conversations: Sequence[ScoredConversation],
    rubric: Rubric,
    summaries: dict[str, str],
    *,
    sample: int | None = None,
    seed: int = 0,
) -> int:
    """Write a sheet for one rater. It is blind: no model name and no judge scores."""
    chosen = list(conversations)
    random.Random(seed).shuffle(chosen)
    if sample is not None:
        chosen = chosen[:sample]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([*FIXED_COLUMNS, *label_columns(rubric)])
        for c in chosen:
            writer.writerow(
                [c.conversation_id, c.scenario_id, summaries[c.persona_id],
                 format_transcript(c.transcript)]
                + [""] * len(label_columns(rubric))
            )  # fmt: skip
    return len(chosen)


def read_sheet(path: Path, rubric: Rubric) -> Labels:
    """Read a filled-in sheet. Blank cells mean "does not apply" and are skipped."""
    columns = label_columns(rubric)
    labels: Labels = {}
    with path.open(newline="", encoding="utf-8") as handle:
        for line, row in enumerate(csv.DictReader(handle), start=2):
            entry: dict[str, float] = {}
            for column in columns:
                cell = (row.get(column) or "").strip()
                if not cell:
                    continue
                try:
                    value = float(cell)
                except ValueError:
                    value = -1.0
                if value not in (0.0, 0.5, 1.0):
                    raise ValueError(
                        f"{path.name} line {line}, column {column}: "
                        f"expected 0, 0.5 or 1, got '{cell}'"
                    )
                entry[column] = value
            if entry:
                labels[row["conversation_id"]] = entry
    return labels


@dataclass(frozen=True)
class MeasureAgreement:
    measure_id: str
    pairs: int
    kappa: float | None
    mean_absolute_error: float | None


@dataclass(frozen=True)
class Comparison:
    measures: list[MeasureAgreement]
    overall: BinaryAgreement | None


def _paired(a: Labels, b: Labels, measure_id: str) -> tuple[list[float], list[float]]:
    left, right = [], []
    for conversation_id in sorted(set(a) & set(b)):
        if measure_id in a[conversation_id] and measure_id in b[conversation_id]:
            left.append(a[conversation_id][measure_id])
            right.append(b[conversation_id][measure_id])
    return left, right


def compare(a: Labels, b: Labels, rubric: Rubric) -> Comparison:
    """Agreement between two sets of labels, per measure and on the overall verdict."""
    rows = []
    for measure_id in label_columns(rubric):
        left, right = _paired(a, b, measure_id)
        if left:
            rows.append(
                MeasureAgreement(
                    measure_id,
                    len(left),
                    weighted_kappa(left, right),
                    mean_absolute_error(left, right),
                )
            )
        else:
            rows.append(MeasureAgreement(measure_id, 0, None, None))

    # Overall verdict: the mean of a conversation's labels, compared at 0.5.
    shared = sorted(set(a) & set(b))
    overall = None
    if shared:
        mean = lambda entry: sum(entry.values()) / len(entry)  # noqa: E731
        overall = binary_agreement([mean(a[c]) for c in shared], [mean(b[c]) for c in shared])
    return Comparison(rows, overall)


def judge_labels(conversations: Sequence[ScoredConversation], rubric: Rubric) -> Labels:
    """The judge's scores in the same shape as a human sheet, snapped to 0 / 0.5 / 1."""
    columns = label_columns(rubric)
    return {
        c.conversation_id: {
            m: nearest_level(c.measure_scores[m])
            for m in columns
            if c.measure_scores.get(m) is not None
        }
        for c in conversations
    }
