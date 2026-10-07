"""Pacing and retries, so free-tier rate limits slow a run down instead of breaking it."""

import asyncio
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence

from mirrorguard.llm.base import ChatModel, Message, RetryableLLMError

Sleep = Callable[[float], Awaitable[None]]


class Throttle:
    """Limits how many calls run at once and how many start per minute.

    One Throttle is shared by every model that uses the same provider account.
    """

    def __init__(
        self,
        *,
        requests_per_minute: int,
        max_concurrency: int,
        clock: Callable[[], float] = time.monotonic,
        sleep: Sleep = asyncio.sleep,
    ):
        if requests_per_minute <= 0 or max_concurrency <= 0:
            raise ValueError("requests_per_minute and max_concurrency must be positive")
        self._interval = 60.0 / requests_per_minute
        self._slots = asyncio.Semaphore(max_concurrency)
        self._pace_lock = asyncio.Lock()
        self._next_start = 0.0
        self._clock = clock
        self._sleep = sleep

    async def __aenter__(self) -> "Throttle":
        await self._slots.acquire()
        async with self._pace_lock:
            now = self._clock()
            wait = self._next_start - now
            self._next_start = max(now, self._next_start) + self._interval
        if wait > 0:
            await self._sleep(wait)
        return self

    async def __aexit__(self, *exc_info) -> None:
        self._slots.release()


class ResilientModel:
    """Wraps a model with shared pacing and retry-with-backoff."""

    def __init__(
        self,
        inner: ChatModel,
        throttle: Throttle,
        *,
        max_retries: int = 6,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        sleep: Sleep = asyncio.sleep,
    ):
        self.name = inner.name
        self._inner = inner
        self._throttle = throttle
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep = sleep

    def _delay(self, attempt: int, exc: RetryableLLMError) -> float:
        if exc.retry_after is not None:
            return min(exc.retry_after, self._max_delay)
        backoff = min(self._base_delay * 2**attempt, self._max_delay)
        return backoff * random.uniform(0.5, 1.0)

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        for attempt in range(self._max_retries + 1):
            try:
                async with self._throttle:
                    return await self._inner.complete(
                        messages, temperature=temperature, max_tokens=max_tokens
                    )
            except RetryableLLMError as exc:
                if attempt == self._max_retries:
                    raise
                await self._sleep(self._delay(attempt, exc))
        raise AssertionError("unreachable")

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        # Retrying is only safe before the first piece of text has been sent on.
        for attempt in range(self._max_retries + 1):
            started = False
            try:
                async with self._throttle:
                    async for piece in self._inner.stream(
                        messages, temperature=temperature, max_tokens=max_tokens
                    ):
                        started = True
                        yield piece
                return
            except RetryableLLMError as exc:
                if started or attempt == self._max_retries:
                    raise
                await self._sleep(self._delay(attempt, exc))
