"""A stand-in model for tests and offline demos. It never calls the network."""

from collections.abc import AsyncIterator, Callable, Sequence

from mirrorguard.llm.base import Message

Responder = Callable[[Sequence[Message]], str]


class FakeModel:
    """Answers from a list of scripted replies, or from a function of the messages."""

    def __init__(self, name: str, replies: Sequence[str] | Responder):
        self.name = name
        self.calls: list[list[Message]] = []
        self._responder = replies if callable(replies) else None
        self._queue = None if callable(replies) else list(replies)

    def _next(self, messages: Sequence[Message]) -> str:
        self.calls.append(list(messages))
        if self._responder is not None:
            return self._responder(messages)
        if not self._queue:
            raise AssertionError(f"FakeModel '{self.name}' ran out of scripted replies")
        return self._queue.pop(0)

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        return self._next(messages)

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        for word in self._next(messages).split(" "):
            yield word + " "
