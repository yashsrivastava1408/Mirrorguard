"""Benchmark reports."""

import pytest

from mirrorguard.benchmark import report
from mirrorguard.benchmark.types import Result
from tests.support.benchmark import CONTROL, MANIA


def result(scenario, persona, model, total, guardrail=False):
    return Result(scenario, persona, model, guardrail, total)


def test_leaderboard_ranks_models_and_shows_the_vulnerability_gap(library):
    results = [
        result(MANIA, "mania", "soft", 0.8),
        result(CONTROL, "control_healthy", "soft", 0.2),
        result(MANIA, "mania", "firm", 0.3),
        result(CONTROL, "control_healthy", "firm", 0.1),
    ]
    board = report.leaderboard(results, library)
    assert [row.target_model for row in board] == ["firm", "soft"]
    soft = board[1]
    assert (soft.conversations, soft.score) == (2, pytest.approx(0.5))
    assert (soft.vulnerable_score, soft.control_score) == (0.8, 0.2)
    assert soft.vulnerability_gap == pytest.approx(0.6)


def test_gap_is_empty_without_a_matched_pair(library):
    board = report.leaderboard([result(MANIA, "mania", "m", 0.5)], library)
    assert board[0].vulnerability_gap is None and board[0].control_score is None


def test_guardrail_effect_compares_off_and_on(library):
    results = [
        result(MANIA, "mania", "m", 0.8),
        result(MANIA, "mania", "m", 0.6),
        result(MANIA, "mania", "m", 0.2, guardrail=True),
        result(CONTROL, "control_healthy", "m", 0.1),
    ]
    effect = report.guardrail_effect(results)
    assert len(effect) == 1
    row = effect[0]
    assert (row.persona_id, row.score_off, row.score_on) == ("mania", pytest.approx(0.7), 0.2)
    assert row.reduction == pytest.approx(0.5)
    assert len(report.by_persona(results)) == 3


def test_table_formatting():
    text = report.format_table(["model", "on", "score"], [["a", True, 0.5], ["bb", False, None]])
    assert text.splitlines() == ["model  on   score", "-----  ---  -----", "a      on   0.500",
                                 "bb     off  -"]  # fmt: skip


def test_scores_are_split_by_language_for_vulnerable_personas(library):
    results = [
        result(MANIA, "mania", "m", 0.4),
        result("hi_mania_quit_job_invest_savings", "mania", "m", 0.8),
        result("hi_ctl_quiet_month", "control_healthy", "m", 0.1),
    ]
    rows = report.by_language(results, library)
    assert [(row.language, row.score) for row in rows] == [("en", 0.4), ("hi-en", 0.8)]
