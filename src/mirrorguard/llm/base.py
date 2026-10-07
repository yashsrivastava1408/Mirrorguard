"""The one interface every model sits behind."""

from collections.abc import AsyncIterator, Sequence
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

Role = Literal["system", "user", "assistant"]


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Role
    content: str


class LLMError(Exception):
    """A model call failed and retrying will not help."""


class RetryableLLMError(LLMError):
    """A model call failed in a way that may pass on retry (rate limit, timeout)."""

    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


class LLMOutputError(LLMError):
    """The model answered, but not in the shape that was asked for."""


@runtime_checkable
class ChatModel(Protocol):
    name: str

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str: ...

    def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...
