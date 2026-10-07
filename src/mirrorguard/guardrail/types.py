"""Plain data used across the guardrail."""

from dataclasses import dataclass, field
from enum import IntEnum, StrEnum


class RiskLevel(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2

    @property
    def label(self) -> str:
        return self.name.lower()

    @classmethod
    def parse(cls, label: str) -> "RiskLevel":
        return cls[label.upper()]


class Action(StrEnum):
    PASS = "pass"  # send the conversation on unchanged
    STEER = "steer"  # add honesty instructions before the chatbot answers
    CHECK = "check"  # steer, then hold the reply and check it before the user sees it


@dataclass(frozen=True)
class RiskAssessment:
    """What the risk scorer made of the latest user message. Not a diagnosis."""

    level: RiskLevel
    signals: tuple[str, ...] = ()
    crisis: bool = False
    from_fallback: bool = False


@dataclass(frozen=True)
class Decision:
    """What the guardrail decided to do for one turn."""

    assessment: RiskAssessment
    session_level: RiskLevel
    action: Action
    shadow: bool = False

    @property
    def applied_action(self) -> Action:
        """In shadow mode the decision is recorded but nothing is changed."""
        return Action.PASS if self.shadow else self.action


@dataclass(frozen=True)
class GuardedReply:
    content: str
    decision: Decision
    rewritten: bool = False
    issues: tuple[str, ...] = ()
    crisis_help_added: bool = False


@dataclass(frozen=True)
class GuardrailEvent:
    """A record of one guarded turn, for the dashboard and the audit trail."""

    tenant_id: str
    session_id: str
    model: str
    user_message: str
    reply: str
    risk_level: str
    session_level: str
    action: str
    shadow: bool
    signals: tuple[str, ...] = ()
    crisis: bool = False
    rewritten: bool = False
    issues: tuple[str, ...] = ()
    original_reply: str | None = None
    from_fallback: bool = False
    extra: dict = field(default_factory=dict)
