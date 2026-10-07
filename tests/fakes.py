"""Scripted stand-ins for the persona, target and judge models."""

import json
import re
from collections.abc import Callable, Sequence

from mirrorguard.llm import Message
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
