"""Plain data passed between the benchmark parts."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Job:
    """One conversation to run: a scenario against one target model."""

    scenario_id: str
    target_model: str
    guardrail: bool = False
    repeat: int = 0

    @property
    def key(self) -> str:
        mode = "on" if self.guardrail else "off"
        return f"{self.scenario_id}|{self.target_model}|guardrail-{mode}|{self.repeat}"


@dataclass(frozen=True)
class ConversationScore:
    """The judge's verdict on one conversation. Every score runs 0 (honest) to 1."""

    judge_model: str
    rubric_version: str
    measure_scores: dict[str, float | None]
    turn_scores: list[dict]
    total: float
    summary: str = ""


@dataclass(frozen=True)
class Result:
    """One scored conversation, as used by the reports."""

    scenario_id: str
    persona_id: str
    target_model: str
    guardrail: bool
    total: float
    measure_scores: dict[str, float | None] = field(default_factory=dict)
