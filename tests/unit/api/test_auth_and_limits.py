"""Key checks and rate limiters."""

import fakeredis
import pytest

from mirrorguard.api.auth import StaticAuthenticator
from mirrorguard.api.ratelimit import MemoryRateLimiter, RedisRateLimiter


async def test_static_authenticator():
    auth = StaticAuthenticator("a:one,b:two")
    assert (await auth.authenticate("b")).id == "two"
    assert await auth.authenticate("c") is None and await auth.authenticate("") is None
    assert await StaticAuthenticator("").authenticate("anything") is None
    with pytest.raises(ValueError):
        StaticAuthenticator("no-tenant")


async def test_memory_rate_limiter_resets_each_minute():
    now = [0.0]
    limiter = MemoryRateLimiter(2, clock=lambda: now[0])
    assert [await limiter.allow("t") for _ in range(3)] == [True, True, False]
    assert await limiter.allow("other")
    now[0] = 61.0
    assert await limiter.allow("t")


async def test_redis_rate_limiter_counts_per_minute():
    now = [0.0]
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    limiter = RedisRateLimiter(redis, 2, clock=lambda: now[0])
    assert [await limiter.allow("t") for _ in range(3)] == [True, True, False]
    assert 0 < await redis.ttl("mg:rate:t:0") <= 120
    now[0] = 61.0
    assert await limiter.allow("t")
