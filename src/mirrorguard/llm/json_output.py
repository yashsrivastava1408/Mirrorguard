"""Asks a model for JSON and checks it, asking again if the answer is malformed."""

import json
import re
from collections.abc import Callable, Sequence
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from mirrorguard.llm.base import ChatModel, LLMOutputError, Message

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def extract_json(text: str) -> str:
    """Pull the JSON object out of a reply that may have fences or chatter around it."""
    cleaned = _FENCE.sub("", text.strip())
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object found")
    return cleaned[start : end + 1]


async def complete_json(
    model: ChatModel,
    messages: Sequence[Message],
    schema: type[T],
    *,
    attempts: int = 3,
    max_tokens: int | None = None,
    check: Callable[[T], None] | None = None,
) -> T:
    """`check` may raise ValueError to reject an answer that parses but is incomplete."""
    conversation = list(messages)
    problem = "no attempt made"
    for _ in range(attempts):
        reply = await model.complete(conversation, temperature=0.0, max_tokens=max_tokens)
        try:
            parsed = schema.model_validate(json.loads(extract_json(reply)))
            if check is not None:
                check(parsed)
            return parsed
        except (ValueError, ValidationError) as exc:
            problem = str(exc)
            conversation += [
                Message(role="assistant", content=reply),
                Message(
                    role="user",
                    content=(
                        f"That reply could not be used: {problem}\n"
                        "Reply again with only the JSON object, nothing else."
                    ),
                ),
            ]
    raise LLMOutputError(
        f"{model.name} did not return valid JSON after {attempts} tries: {problem}"
    )
