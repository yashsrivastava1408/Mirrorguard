"""Shapes of the test material: personas, scenarios and the scoring rubric."""

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Identifier = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$")]
Text = Annotated[str, Field(min_length=1)]


class VulnerabilityState(StrEnum):
    NONE = "none"
    DEPRESSION = "depression"
    MANIA = "mania"
    DELUSION = "delusion"
    EATING_DISORDER = "eating_disorder"
    CONSPIRACY_SPIRAL = "conspiracy_spiral"
    AI_DEPENDENCE = "ai_dependence"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Arc(_Strict):
    """How the persona changes over a conversation."""

    early: Text
    middle: Text
    late: Text


class Persona(_Strict):
    """A pretend user, played by an AI, used for testing."""

    id: Identifier
    name: Text
    vulnerability_state: VulnerabilityState
    is_control: bool = False
    summary: Text
    background: Text
    speaking_style: Text
    core_belief: Text
    risk_signals: list[Text] = Field(default_factory=list)
    pressure_tactics: list[Text] = Field(min_length=2)
    arc: Arc

    @model_validator(mode="after")
    def _control_matches_state(self) -> "Persona":
        healthy = self.vulnerability_state is VulnerabilityState.NONE
        if self.is_control != healthy:
            raise ValueError("is_control must be true exactly when vulnerability_state is 'none'")
        if self.is_control and self.risk_signals:
            raise ValueError("a control persona must not have risk signals")
        if not self.is_control and len(self.risk_signals) < 2:
            raise ValueError("a vulnerable persona needs at least two risk signals")
        return self


class Scenario(_Strict):
    """One situation a persona brings to the chatbot."""

    id: Identifier
    title: Text
    persona_id: Identifier
    language: Literal["en", "hi", "hi-en"] = "en"
    opening_message: Text
    user_goal: Text
    sycophantic_reply_would: list[Text] = Field(min_length=1)
    honest_reply_should: list[Text] = Field(min_length=1)
    pushback_lines: list[Text] = Field(min_length=2)
    turns: int = Field(default=20, ge=6, le=40)
    escalation_expected: bool = False
    matched_control: Identifier | None = None


class Anchors(_Strict):
    """What a score of 0, 0.5 and 1 looks like for one measure."""

    zero: Text
    half: Text
    one: Text


class Measure(_Strict):
    """One thing the judge scores, from 0 (good) to 1 (bad)."""

    id: Identifier
    name: Text
    question: Text
    weight: float = Field(gt=0, le=1)
    level: Literal["turn", "conversation"] = "turn"
    applies_when: Literal["always", "escalation_expected"] = "always"
    anchors: Anchors


class Rubric(_Strict):
    version: Text
    measures: list[Measure] = Field(min_length=1)

    @model_validator(mode="after")
    def _weights_are_consistent(self) -> "Rubric":
        ids = [m.id for m in self.measures]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate measure ids: {', '.join(duplicates)}")
        total = sum(m.weight for m in self.measures)
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"measure weights must add up to 1, got {total:.4f}")
        return self

    def measure(self, measure_id: str) -> Measure:
        for m in self.measures:
            if m.id == measure_id:
                return m
        raise KeyError(measure_id)
