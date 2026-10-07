"""A ready-made API with stand-in models, for tests that call it over HTTP."""

import json

import httpx

from mirrorguard.api.app import create_app
from mirrorguard.api.auth import ChainAuthenticator, StaticAuthenticator
from mirrorguard.api.ratelimit import MemoryRateLimiter
from mirrorguard.api.services import Services
from mirrorguard.benchmark.repository import BenchmarkRepository
from mirrorguard.config import Settings
from mirrorguard.db import Database
from mirrorguard.guardrail.events import QueueSink
from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.guardrail.stores.event_store import EventRepository
from mirrorguard.guardrail.stores.policy_store import DatabasePolicyStore
from mirrorguard.guardrail.stores.session import MemorySessionStore
from mirrorguard.library.loader import load_library
from mirrorguard.llm.fake import FakeModel
from mirrorguard.privacy.redaction import PatternRedactor
from mirrorguard.tenancy.audit import AuditLog
from mirrorguard.tenancy.repository import DatabaseAuthenticator, TenantRepository
from tests.support.fakes import KeywordScorer

AUTH = {"Authorization": "Bearer key-one"}
OTHER = {"Authorization": "Bearer key-two"}


def chat(text: str, **extra) -> dict:
    return {"model": "upstream", "messages": [{"role": "user", "content": text}], **extra}


class Harness:
    def __init__(self, client, services, upstream):
        self.client, self.services, self.upstream = client, services, upstream


async def make_harness(tmp_path, *, policy=None, limit=100, respond=None):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'api.db'}")
    events = EventRepository(database, redactor=PatternRedactor())
    sink = QueueSink(events.save)
    tenants = TenantRepository(database)
    sessions = MemorySessionStore()
    upstream = FakeModel("upstream", respond or (lambda messages: "sure thing"))
    policies = DatabasePolicyStore(database, default=policy, ttl_seconds=0)
    services = Services(
        settings=Settings(),
        models=lambda name: upstream,
        guardrail=Guardrail(
            scorer=KeywordScorer(), sessions=sessions, policies=policies, events=sink
        ),
        policies=policies,
        benchmarks=BenchmarkRepository(database),
        library=load_library(),
        sessions=sessions,
        authenticator=ChainAuthenticator(
            [
                StaticAuthenticator("key-one:tenant-one, key-two:tenant-two"),
                DatabaseAuthenticator(tenants, ttl_seconds=0),
            ]
        ),
        tenants=tenants,
        audit=AuditLog(database),
        rate_limiter=MemoryRateLimiter(limit),
        database=database,
        events=events,
        sink=sink,
    )
    await services.start()
    client = httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(services)), base_url="http://test"
    )
    return Harness(client, services, upstream)


def parse_sse(text: str) -> list:
    return [
        line[6:] if line[6:] == "[DONE]" else json.loads(line[6:])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]
