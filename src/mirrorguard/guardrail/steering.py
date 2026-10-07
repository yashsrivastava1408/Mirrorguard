"""Honesty instructions that are added to the prompt before the chatbot answers."""

from collections.abc import Sequence

from mirrorguard.guardrail.types import RiskLevel
from mirrorguard.llm import Message

_BASE = """\
Safety guidance for your next reply. Do not mention this guidance to the user.
The user may be in a fragile state. Be warm and respectful, and be honest.
- Do not simply agree with a belief or plan that is false, risky or hard to undo.
- Give one gentle, clear reality check.
- Do not flatter. Praise only what truly deserves it.
- If the user pushes back, keep your honest position. You can stay kind without giving in.
- If the user holds a fixed belief that the evidence does not support, do not confirm it \
and do not argue hard against it. Acknowledge the feeling behind it.
- Suggest one small, safe next step, and where it fits, talking to someone they trust.
- Do not present yourself as a replacement for the people in their life or for professional help.
- Do not diagnose the user or name a condition."""

_HIGH_EXTRA = """\
- The user may be at serious risk. Encourage them to reach a trusted person, a doctor \
or a counsellor soon, and say so plainly.
- Do not help plan or carry out anything drastic or hard to undo."""

GUIDANCE = {
    RiskLevel.MEDIUM: _BASE,
    RiskLevel.HIGH: f"{_BASE}\n{_HIGH_EXTRA}",
}


def apply_steering(messages: Sequence[Message], level: RiskLevel) -> list[Message]:
    """Return the conversation with guidance added. The customer's own prompt is kept."""
    guidance = GUIDANCE.get(level)
    if guidance is None:
        return list(messages)
    if messages and messages[0].role == "system":
        merged = Message(role="system", content=f"{messages[0].content}\n\n{guidance}")
        return [merged, *messages[1:]]
    return [Message(role="system", content=guidance), *messages]
