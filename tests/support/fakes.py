"""Scripted stand-ins for models and guardrail parts, and small builders for test data."""

import json
import re
from collections.abc import Callable, Sequence

from mirrorguard.guardrail.types import GuardrailEvent, RiskAssessment, RiskLevel
from mirrorguard.llm import LLMError, Message
from mirrorguard.llm.fake import FakeModel

_TURNS = re.compile(r"Score turns (\d+) to (\d+)")


_KEYS = re.compile(r'"([a-z_]+)": 0')


def judge_model(
    turn_score: Callable[[int, str], float | None] = lambda turn, measure: 0.0,
    conversation_score: Callable[[str], float | None] = lambda measure: 0.0,
    name: str = "fake-judge",
) -> FakeModel:
    """A judge that answers in the right JSON shape with scores from the given functions."""

    def respond(messages: Sequence[Message]) -> str:
        # messages[1] is the task; later messages only appear when the judge is asked again
        task = messages[1].content.rsplit("Reply with only this JSON", 1)
        keys = _KEYS.findall(task[1])
        batch = _TURNS.search(task[0])
        if batch:
            first, last = int(batch.group(1)), int(batch.group(2))
            turns = [
                {"turn": n, "scores": {k: turn_score(n, k) for k in keys}, "note": "n"}
                for n in range(first, last + 1)
            ]
            return json.dumps({"turns": turns})
        return json.dumps({"scores": {k: conversation_score(k) for k in keys}, "summary": "s"})

    return FakeModel(name, respond)


def echo_model(name: str, text: str = "reply") -> FakeModel:
    """Always answers with the same text plus a running number."""
    counter = iter(range(1, 10_000))
    return FakeModel(name, lambda messages: f"{text} {next(counter)}")


LOW, MEDIUM, HIGH = RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH


def user(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


class KeywordScorer:
    """Risk from keywords in the latest message, so tests read plainly."""

    def __init__(self):
        self.calls = 0

    async def assess(self, messages):
        self.calls += 1
        text = messages[-1].content.lower()
        if "scorer-down" in text:
            raise LLMError("scorer is down")
        if "end it all" in text:
            return RiskAssessment(HIGH, ("self-harm",), crisis=True)
        if "tonight" in text:
            return RiskAssessment(HIGH, ("drastic step",))
        if "not slept" in text:
            return RiskAssessment(MEDIUM, ("no sleep",))
        return RiskAssessment(LOW)


class StubReplyGuard:
    async def review(self, messages, reply, *, max_rewrites):
        return "a safer reply", ("agreed with a risky plan",)


def make_event(**changes) -> GuardrailEvent:
    base = {
        "tenant_id": "t", "session_id": "s", "model": "m", "user_message": "u", "reply": "r",
        "risk_level": "medium", "session_level": "medium", "action": "steer", "shadow": False,
    }  # fmt: skip
    return GuardrailEvent(**{**base, **changes})
