"""Pacing and retries."""

import asyncio

import pytest

from mirrorguard.llm import Message, RetryableLLMError
from mirrorguard.llm.resilient import ResilientModel, Throttle

HELLO = [Message(role="user", content="hello")]


class FlakyModel:
    """Fails a set number of times, then answers."""

    name = "flaky"

    def __init__(self, failures: int, retry_after: float | None = None):
        self.failures = failures
        self.retry_after = retry_after
        self.attempts = 0

    async def complete(self, messages, *, temperature=0.7, max_tokens=None):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RetryableLLMError("rate limited", retry_after=self.retry_after)
        return "fine"

    async def stream(self, messages, *, temperature=0.7, max_tokens=None):
        self.attempts += 1
        if self.attempts <= self.failures:
            raise RetryableLLMError("rate limited")
        yield "a "
        yield "b"


class Recorder:
    def __init__(self):
        self.sleeps: list[float] = []

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def throttle(**overrides):
    return Throttle(**{"requests_per_minute": 6000, "max_concurrency": 8, **overrides})


async def test_throttle_spaces_out_call_starts():
    now = [0.0]
    recorder = Recorder()
    limiter = Throttle(
        requests_per_minute=60, max_concurrency=5, clock=lambda: now[0], sleep=recorder.sleep
    )
    for _ in range(3):
        async with limiter:
            pass
    assert recorder.sleeps == [1.0, 2.0]


async def test_throttle_limits_calls_running_at_once():
    limiter = throttle(max_concurrency=2)
    running = peak = 0

    async def work():
        nonlocal running, peak
        async with limiter:
            running += 1
            peak = max(peak, running)
            await asyncio.sleep(0.01)
            running -= 1

    await asyncio.gather(*(work() for _ in range(8)))
    assert peak == 2


def test_throttle_rejects_bad_limits():
    with pytest.raises(ValueError):
        Throttle(requests_per_minute=0, max_concurrency=1)


async def test_retries_until_the_call_succeeds():
    inner, recorder = FlakyModel(failures=2), Recorder()
    model = ResilientModel(inner, throttle(), max_retries=3, sleep=recorder.sleep)
    assert await model.complete(HELLO) == "fine"
    assert inner.attempts == 3 and len(recorder.sleeps) == 2
    assert recorder.sleeps[1] > recorder.sleeps[0] * 0.99  # backoff grows


async def test_gives_up_after_max_retries():
    inner = FlakyModel(failures=10)
    model = ResilientModel(inner, throttle(), max_retries=2, sleep=Recorder().sleep)
    with pytest.raises(RetryableLLMError):
        await model.complete(HELLO)
    assert inner.attempts == 3


async def test_waits_as_long_as_the_provider_asks():
    recorder = Recorder()
    model = ResilientModel(
        FlakyModel(failures=1, retry_after=7.0), throttle(), sleep=recorder.sleep
    )
    await model.complete(HELLO)
    assert recorder.sleeps == [7.0]


async def test_stream_retries_before_any_text_is_sent():
    inner = FlakyModel(failures=1)
    model = ResilientModel(inner, throttle(), sleep=Recorder().sleep)
    assert [piece async for piece in model.stream(HELLO)] == ["a ", "b"]
    assert inner.attempts == 2
