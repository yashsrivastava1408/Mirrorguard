"""Reads the user's latest message and decides how risky the moment is."""

from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel, Field

from mirrorguard.guardrail.types import RiskAssessment, RiskLevel
from mirrorguard.llm import ChatModel, Message, complete_json

_SYSTEM = """\
You are a safety screen for a chat assistant. You read the latest messages from a user \
and decide how much care the assistant's next reply needs. You do not diagnose anyone. \
You only notice signals in what the user wrote.

Signals to look for
- Very little sleep together with very high energy, grand plans or sudden big money decisions.
- Hopelessness, feeling like a burden, pulling away from everyone, giving up on things.
- A fixed belief of being watched, followed or targeted, with coincidences treated as proof.
- Pride in not eating, fear of weight gain, hiding eating from family.
- A belief that one hidden group controls everything, with family cut off for disagreeing.
- Treating the assistant as a replacement for friends, family or a therapist.
- Any mention of wanting to die, self-harm, or harming someone else.

Levels
- "low": an ordinary message. No signals, or a calm and well-grounded user.
- "medium": one or more signals, and the user wants agreement with a belief or plan \
that could hurt them.
- "high": strong or repeated signals together with a drastic or hard-to-undo step that \
is about to happen, or any sign of danger to the user or to others.

Set "crisis" to true only for thoughts of suicide, self-harm, or harming someone else.

Reply with only this JSON:
{"level": "low", "signals": ["short phrase for each signal you noticed"], "crisis": false}"""


class _Answer(BaseModel):
    level: Literal["low", "medium", "high"]
    signals: list[str] = Field(default_factory=list)
    crisis: bool = False


class RiskScorer(Protocol):
    async def assess(self, messages: Sequence[Message]) -> RiskAssessment: ...


class LLMRiskScorer:
    """Uses a small, fast model. It sees only the last few messages, to stay quick."""

    def __init__(self, model: ChatModel, *, window: int = 6, max_tokens: int = 200):
        self._model = model
        self._window = window
        self._max_tokens = max_tokens

    async def assess(self, messages: Sequence[Message]) -> RiskAssessment:
        recent = [m for m in messages if m.role != "system"][-self._window :]
        shown = "\n".join(f"{m.role.upper()}: {m.content}" for m in recent)
        answer = await complete_json(
            self._model,
            [
                Message(role="system", content=_SYSTEM),
                Message(role="user", content=f"Conversation so far\n{shown}"),
            ],
            _Answer,
            attempts=2,
            max_tokens=self._max_tokens,
        )
        level = RiskLevel.parse(answer.level)
        if answer.crisis:
            level = RiskLevel.HIGH
        return RiskAssessment(level=level, signals=tuple(answer.signals), crisis=answer.crisis)
