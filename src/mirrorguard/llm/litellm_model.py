"""Real models, reached through LiteLLM so any provider works with one code path."""

from collections.abc import AsyncIterator, Sequence

import litellm

from mirrorguard.llm.base import LLMError, Message, RetryableLLMError

litellm.suppress_debug_info = True

_RETRYABLE = (
    litellm.RateLimitError,
    litellm.Timeout,
    litellm.APIConnectionError,
    litellm.InternalServerError,
    litellm.ServiceUnavailableError,
)


def _retry_after(exc: Exception) -> float | None:
    headers = getattr(getattr(exc, "response", None), "headers", None) or {}
    try:
        return float(headers.get("retry-after"))
    except (TypeError, ValueError):
        return None


class LiteLLMModel:
    def __init__(
        self,
        name: str,
        *,
        timeout: float = 60.0,
        api_base: str | None = None,
        api_key: str | None = None,
    ):
        self.name = name
        self._options = {"model": name, "timeout": timeout, "num_retries": 0}
        if api_base:
            self._options["api_base"] = api_base
        if api_key:
            self._options["api_key"] = api_key

    async def _call(self, messages: Sequence[Message], **extra):
        payload = [m.model_dump() for m in messages]
        extra = {key: value for key, value in extra.items() if value is not None}
        try:
            return await litellm.acompletion(messages=payload, **self._options, **extra)
        except _RETRYABLE as exc:
            raise RetryableLLMError(str(exc), retry_after=_retry_after(exc)) from exc
        except Exception as exc:
            raise LLMError(f"{self.name}: {exc}") from exc

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        response = await self._call(messages, temperature=temperature, max_tokens=max_tokens)
        return response.choices[0].message.content or ""

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        response = await self._call(
            messages, temperature=temperature, max_tokens=max_tokens, stream=True
        )
        try:
            async for chunk in response:
                text = chunk.choices[0].delta.content if chunk.choices else None
                if text:
                    yield text
        except _RETRYABLE as exc:
            raise RetryableLLMError(str(exc), retry_after=_retry_after(exc)) from exc
