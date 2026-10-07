"""Turns scored conversations into the tables people read."""

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from statistics import fmean

from mirrorguard.benchmark.types import Result
from mirrorguard.loader import Library


@dataclass(frozen=True)
class LeaderboardRow:
    target_model: str
    guardrail: bool
    conversations: int
    score: float
    vulnerable_score: float | None
    control_score: float | None
    vulnerability_gap: float | None


@dataclass(frozen=True)
class PersonaRow:
    target_model: str
    guardrail: bool
    persona_id: str
    conversations: int
    score: float


@dataclass(frozen=True)
class GuardrailEffectRow:
    target_model: str
    persona_id: str
    score_off: float
    score_on: float
    reduction: float


def _mean(values: Sequence[float]) -> float | None:
    return fmean(values) if values else None


def _matched_gap(results: Sequence[Result], library: Library) -> float | None:
    """Average of (vulnerable scenario score minus its matched control score)."""
    by_scenario: dict[str, list[float]] = defaultdict(list)
    for r in results:
        by_scenario[r.scenario_id].append(r.total)
    gaps = []
    for scenario_id, totals in by_scenario.items():
        control_id = library.scenarios[scenario_id].matched_control
        if control_id and control_id in by_scenario:
            gaps.append(fmean(totals) - fmean(by_scenario[control_id]))
    return _mean(gaps)


def leaderboard(results: Sequence[Result], library: Library) -> list[LeaderboardRow]:
    """One row per target model and guardrail mode. Lower scores are better."""
    groups: dict[tuple[str, bool], list[Result]] = defaultdict(list)
    for r in results:
        groups[(r.target_model, r.guardrail)].append(r)
    rows = []
    for (model, guardrail), group in groups.items():
        vulnerable = [r.total for r in group if not library.personas[r.persona_id].is_control]
        control = [r.total for r in group if library.personas[r.persona_id].is_control]
        rows.append(
            LeaderboardRow(
                target_model=model,
                guardrail=guardrail,
                conversations=len(group),
                score=fmean(r.total for r in group),
                vulnerable_score=_mean(vulnerable),
                control_score=_mean(control),
                vulnerability_gap=_matched_gap(group, library),
            )
        )
    return sorted(rows, key=lambda row: (row.vulnerable_score or row.score, row.target_model))


def by_persona(results: Sequence[Result]) -> list[PersonaRow]:
    groups: dict[tuple[str, bool, str], list[float]] = defaultdict(list)
    for r in results:
        groups[(r.target_model, r.guardrail, r.persona_id)].append(r.total)
    return [
        PersonaRow(model, guardrail, persona_id, len(totals), fmean(totals))
        for (model, guardrail, persona_id), totals in sorted(groups.items())
    ]


@dataclass(frozen=True)
class LanguageRow:
    target_model: str
    guardrail: bool
    language: str
    conversations: int
    score: float


def by_language(results: Sequence[Result], library: Library) -> list[LanguageRow]:
    """Scores split by scenario language, for vulnerable personas only."""
    groups: dict[tuple[str, bool, str], list[float]] = defaultdict(list)
    for r in results:
        if not library.personas[r.persona_id].is_control:
            language = library.scenarios[r.scenario_id].language
            groups[(r.target_model, r.guardrail, language)].append(r.total)
    return [
        LanguageRow(model, guardrail, language, len(totals), fmean(totals))
        for (model, guardrail, language), totals in sorted(groups.items())
    ]


def guardrail_effect(results: Sequence[Result]) -> list[GuardrailEffectRow]:
    """For each model and persona, the score with the guardrail off and on."""
    scores = {(r.target_model, r.guardrail, r.persona_id): r.score for r in by_persona(results)}
    rows = []
    for (model, guardrail, persona_id), off in sorted(scores.items()):
        on = scores.get((model, True, persona_id))
        if guardrail or on is None:
            continue
        rows.append(GuardrailEffectRow(model, persona_id, off, on, off - on))
    return rows


def format_table(headers: Sequence[str], rows: Sequence[Sequence[object]]) -> str:
    def cell(value: object) -> str:
        if value is None:
            return "-"
        if isinstance(value, bool):
            return "on" if value else "off"
        if isinstance(value, float):
            return f"{value:.3f}"
        return str(value)

    table = [list(headers), *([cell(v) for v in row] for row in rows)]
    widths = [max(len(row[i]) for row in table) for i in range(len(headers))]
    lines = [
        "  ".join(text.ljust(width) for text, width in zip(row, widths, strict=True))
        for row in table
    ]
    lines.insert(1, "  ".join("-" * width for width in widths))
    return "\n".join(line.rstrip() for line in lines)
