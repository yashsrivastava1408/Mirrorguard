"""Builds everything the API needs, once, at start-up."""

from dataclasses import dataclass

from mirrorguard.api.auth import Authenticator, StaticAuthenticator
from mirrorguard.api.ratelimit import MemoryRateLimiter, RateLimiter, RedisRateLimiter
from mirrorguard.benchmark.repository import BenchmarkRepository
from mirrorguard.config import Settings
from mirrorguard.db import Database
from mirrorguard.guardrail.event_store import EventRepository
from mirrorguard.guardrail.events import QueueSink
from mirrorguard.guardrail.factory import build_guardrail
from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.guardrail.policy_store import DatabasePolicyStore
from mirrorguard.guardrail.session import MemorySessionStore, RedisSessionStore, SessionStore
from mirrorguard.llm.factory import ModelFactory, make_model_factory
from mirrorguard.loader import Library, load_library


@dataclass
class Services:
    settings: Settings
    models: ModelFactory
    guardrail: Guardrail
    sessions: SessionStore
    authenticator: Authenticator
    rate_limiter: RateLimiter
    database: Database | None = None
    events: EventRepository | None = None
    policies: DatabasePolicyStore | None = None
    benchmarks: BenchmarkRepository | None = None
    library: Library | None = None
    sink: QueueSink | None = None
    redis: object | None = None

    async def start(self) -> None:
        if self.database is not None:
            await self.database.create_tables()
        if self.sink is not None:
            self.sink.start()

    async def stop(self) -> None:
        if self.sink is not None:
            await self.sink.stop()
        if self.redis is not None:
            await self.redis.aclose()
        if self.database is not None:
            await self.database.dispose()


def build_services(settings: Settings) -> Services:
    """With MG_REDIS_URL set, session state and rate limits are shared across servers."""
    models = make_model_factory(settings)
    database = Database(settings.database_url)
    events = EventRepository(database)
    sink = QueueSink(events.save)
    policies = DatabasePolicyStore(database)

    redis = None
    if settings.redis_url:
        from redis.asyncio import Redis

        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        sessions: SessionStore = RedisSessionStore(redis, ttl_seconds=settings.session_ttl_seconds)
        rate_limiter: RateLimiter = RedisRateLimiter(redis, settings.tenant_requests_per_minute)
    else:
        sessions = MemorySessionStore()
        rate_limiter = MemoryRateLimiter(settings.tenant_requests_per_minute)

    return Services(
        settings=settings,
        models=models,
        guardrail=build_guardrail(
            settings, models, sessions=sessions, policies=policies, events=sink
        ),
        sessions=sessions,
        authenticator=StaticAuthenticator(settings.api_keys),
        rate_limiter=rate_limiter,
        database=database,
        events=events,
        policies=policies,
        benchmarks=BenchmarkRepository(database),
        library=load_library(),
        sink=sink,
        redis=redis,
    )
