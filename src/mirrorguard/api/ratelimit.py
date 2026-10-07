"""Limits how many requests one tenant can make per minute."""

import time
from collections.abc import Callable
from typing import Protocol


class RateLimiter(Protocol):
    async def allow(self, key: str) -> bool: ...


class MemoryRateLimiter:
    """Counts per minute inside one process. For tests and local runs."""

    def __init__(self, limit: int, clock: Callable[[], float] = time.time):
        self._limit = limit
        self._clock = clock
        self._window = -1
        self._counts: dict[str, int] = {}

    async def allow(self, key: str) -> bool:
        window = int(self._clock() // 60)
        if window != self._window:
            self._window, self._counts = window, {}
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key] <= self._limit


class RedisRateLimiter:
    """Counts per minute in Redis, so the limit holds across every copy of the server."""

    def __init__(self, redis, limit: int, clock: Callable[[], float] = time.time):
        self._redis = redis
        self._limit = limit
        self._clock = clock

    async def allow(self, key: str) -> bool:
        bucket = f"mg:rate:{key}:{int(self._clock() // 60)}"
        count = await self._redis.incr(bucket)
        if count == 1:
            await self._redis.expire(bucket, 120)
        return count <= self._limit
