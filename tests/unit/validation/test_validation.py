"""Agreement statistics and labelling sheets."""

import csv

import pytest

from mirrorguard.benchmark.repository import ScoredConversation
from mirrorguard.llm import Message
from mirrorguard.validation import labels
from mirrorguard.validation.agreement import (
    binary_agreement,
    mean_absolute_error,
    nearest_level,
    weighted_kappa,
)


def test_identical_labels_agree_perfectly():
    assert weighted_kappa([0, 0.5, 1, 1], [0, 0.5, 1, 1]) == pytest.approx(1.0)


def test_opposite_labels_are_worse_than_chance():
    assert weighted_kappa([0, 0, 1, 1], [1, 1, 0, 0]) == pytest.approx(-1.0)


def test_kappa_matches_a_hand_worked_example():
    # Two near misses in eight pairs: observed disagreement 2/16 = 0.125.
    # Chance disagreement from the label counts (3,2,3 against 2,4,2) is 0.4375.
    # Kappa = 1 - 0.125 / 0.4375 = 5/7.
    a = [0, 0, 0.5, 0.5, 1, 1, 0, 1]
    b = [0, 0.5, 0.5, 0.5, 1, 0.5, 0, 1]
    assert weighted_kappa(a, b) == pytest.approx(5 / 7)


def test_kappa_when_only_one_label_is_ever_used():
    assert weighted_kappa([0, 0, 0], [0, 0, 0]) == 1.0


def test_kappa_rejects_bad_input():
    with pytest.raises(ValueError, match="same length"):
        weighted_kappa([0], [0, 1])
    with pytest.raises(ValueError, match="at least one"):
        weighted_kappa([], [])
    with pytest.raises(ValueError, match="0, 0.5 or 1"):
        weighted_kappa([0.3], [0])


def test_mean_absolute_error():
    assert mean_absolute_error([0, 1, 0.5], [0, 0, 1]) == pytest.approx(0.5)


@pytest.mark.parametrize(("value", "level"), [(0.1, 0.0), (0.25, 0.0), (0.3, 0.5), (0.8, 1.0)])
def test_scores_snap_to_the_nearest_level(value, level):
    assert nearest_level(value) == level


def test_binary_agreement():
    result = binary_agreement([0.9, 0.6, 0.1, 0.2], [1.0, 0.0, 0.0, 1.0])
    assert (result.precision, result.recall, result.accuracy) == (0.5, 0.5, 0.5)
    assert result.f1 == pytest.approx(0.5)


def test_binary_agreement_without_any_positive_case():
    result = binary_agreement([0.0, 0.1], [0.0, 0.2])
    assert (result.precision, result.recall, result.f1, result.accuracy) == (None, None, None, 1.0)


def conversation(conversation_id, scores):
    return ScoredConversation(
        conversation_id=conversation_id,
        scenario_id="mania_quit_job_invest_savings",
        persona_id="mania",
        target_model="secret-model",
        guardrail=False,
        transcript=[Message(role="user", content="hi"), Message(role="assistant", content="yo")],
        measure_scores=scores,
        total=0.5,
        summary="",
    )


def test_sheet_is_blind_and_leaves_out_computed_measures(tmp_path, library):
    path = tmp_path / "sheet.csv"
    summaries = {"mania": "summary text"}
    count = labels.write_sheet(path, [conversation("c1", {})], library.rubric, summaries)
    text = path.read_text()
    assert count == 1
    assert "secret-model" not in text and "drift" not in text
    header = text.splitlines()[0].split(",")
    assert header[:4] == labels.FIXED_COLUMNS and "harmful_validation" in header
    assert "USER: hi" in text and "summary text" in text


def test_sheet_sampling_is_repeatable(tmp_path, library):
    conversations = [conversation(f"c{n}", {}) for n in range(10)]
    summaries = {"mania": "s"}
    first, second = tmp_path / "a.csv", tmp_path / "b.csv"
    labels.write_sheet(first, conversations, library.rubric, summaries, sample=4, seed=1)
    labels.write_sheet(second, conversations, library.rubric, summaries, sample=4, seed=1)
    assert first.read_text() == second.read_text()
    with first.open(newline="") as handle:
        assert len(list(csv.DictReader(handle))) == 4


def fill(path, rows, library):
    columns = labels.label_columns(library.rubric)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([*labels.FIXED_COLUMNS, *columns])
        for conversation_id, values in rows.items():
            writer.writerow([conversation_id, "s", "u", "t", *[values.get(c, "") for c in columns]])


def test_filled_sheet_is_read_and_blanks_are_skipped(tmp_path, library):
    path = tmp_path / "rater.csv"
    fill(path, {"c1": {"harmful_validation": 1, "excessive_flattery": 0.5}, "c2": {}}, library)
    assert labels.read_sheet(path, library.rubric) == {
        "c1": {"harmful_validation": 1.0, "excessive_flattery": 0.5}
    }


def test_bad_label_is_reported_with_its_place(tmp_path, library):
    path = tmp_path / "rater.csv"
    fill(path, {"c1": {"harmful_validation": "high"}}, library)
    with pytest.raises(ValueError, match="line 2, column harmful_validation.*'high'"):
        labels.read_sheet(path, library.rubric)


def test_judge_is_compared_with_a_rater(library):
    judge = labels.judge_labels(
        [
            conversation("c1", {"harmful_validation": 0.9, "excessive_flattery": 0.1}),
            conversation("c2", {"harmful_validation": 0.1, "excessive_flattery": None}),
        ],
        library.rubric,
    )
    assert judge == {
        "c1": {"harmful_validation": 1.0, "excessive_flattery": 0.0},
        "c2": {"harmful_validation": 0.0},
    }
    rater = {"c1": {"harmful_validation": 1.0}, "c2": {"harmful_validation": 0.0}, "c3": {}}
    comparison = labels.compare(judge, rater, library.rubric)
    by_measure = {m.measure_id: m for m in comparison.measures}
    assert by_measure["harmful_validation"].pairs == 2
    assert by_measure["harmful_validation"].kappa == pytest.approx(1.0)
    assert by_measure["excessive_flattery"].pairs == 0
    assert by_measure["excessive_flattery"].kappa is None
    assert comparison.overall.accuracy == 1.0
