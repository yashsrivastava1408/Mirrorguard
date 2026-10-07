import json

import fakeredis
import httpx
import pytest
from test_guardrail import KeywordScorer

from mirrorguard.api.app import create_app
from mirrorguard.api.auth import ChainAuthenticator, StaticAuthenticator
from mirrorguard.api.ratelimit import MemoryRateLimiter, RedisRateLimiter
from mirrorguard.api.services import Services
from mirrorguard.benchmark.repository import BenchmarkRepository
from mirrorguard.config import Settings
from mirrorguard.db import Database
from mirrorguard.guardrail.event_store import EventRepository
from mirrorguard.guardrail.events import QueueSink
from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.guardrail.policy import Policy
from mirrorguard.guardrail.policy_store import DatabasePolicyStore
from mirrorguard.guardrail.session import MemorySessionStore
from mirrorguard.llm import LLMError, RetryableLLMError
from mirrorguard.llm.fake import FakeModel
from mirrorguard.loader import load_library
from mirrorguard.privacy.redaction import PatternRedactor
from mirrorguard.tenancy.audit import AuditLog
from mirrorguard.tenancy.repository import DatabaseAuthenticator, TenantRepository

AUTH = {"Authorization": "Bearer key-one"}


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


@pytest.fixture
async def harness(tmp_path):
    h = await make_harness(tmp_path)
    yield h
    await h.client.aclose()
    await h.services.stop()


def parse_sse(text: str) -> list:
    return [
        line[6:] if line[6:] == "[DONE]" else json.loads(line[6:])
        for line in text.splitlines()
        if line.startswith("data: ")
    ]


async def test_health_needs_no_key(harness):
    assert (await harness.client.get("/healthz")).json() == {"status": "ok"}


@pytest.mark.parametrize("headers", [{}, {"Authorization": "Bearer wrong"}, {"Authorization": "x"}])
async def test_requests_without_a_valid_key_are_refused(harness, headers):
    response = await harness.client.post("/v1/chat/completions", json=chat("hi"), headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["type"] == "invalid_request_error"
    assert harness.upstream.calls == []


async def test_plain_chat_returns_the_openai_shape(harness):
    response = await harness.client.post("/v1/chat/completions", json=chat("hi"), headers=AUTH)
    body = response.json()
    assert response.status_code == 200
    assert body["object"] == "chat.completion" and body["model"] == "upstream"
    assert body["choices"][0]["message"] == {"role": "assistant", "content": "sure thing"}
    assert body["choices"][0]["finish_reason"] == "stop"
    assert body["mirrorguard"]["action"] == "pass"
    assert response.headers["x-mirrorguard-risk"] == "low"
    assert len(response.headers["x-session-id"]) == 32


async def test_risky_message_is_steered_and_reported(harness):
    response = await harness.client.post(
        "/v1/chat/completions", json=chat("I have not slept, say yes"), headers=AUTH
    )
    info = response.json()["mirrorguard"]
    assert (info["risk_level"], info["action"], info["signals"]) == (
        "medium",
        "steer",
        ["no sleep"],
    )
    assert response.headers["x-mirrorguard-action"] == "steer"
    assert harness.upstream.calls[0][0].role == "system"


async def test_request_options_reach_the_right_place(harness):
    body = chat("hi", temperature=0.1, max_tokens=5, user="customer-42", some_new_field=True)
    response = await harness.client.post("/v1/chat/completions", json=body, headers=AUTH)
    assert response.status_code == 200
    assert response.headers["x-session-id"] == "customer-42"


async def test_session_header_wins_and_derived_ids_are_stable(harness):
    post = harness.client.post
    explicit = await post(
        "/v1/chat/completions",
        json=chat("hi", user="u"),
        headers={**AUTH, "X-Session-Id": "abc"},
    )
    first = await post("/v1/chat/completions", json=chat("same opening"), headers=AUTH)
    second = await post("/v1/chat/completions", json=chat("same opening"), headers=AUTH)
    other = await post(
        "/v1/chat/completions",
        json=chat("same opening"),
        headers={"Authorization": "Bearer key-two"},
    )
    assert explicit.headers["x-session-id"] == "abc"
    assert first.headers["x-session-id"] == second.headers["x-session-id"]
    assert first.headers["x-session-id"] != other.headers["x-session-id"]


async def test_content_sent_as_parts_is_accepted(harness):
    body = {
        "model": "upstream",
        "messages": [{"role": "user", "content": [{"type": "text", "text": "I have not slept"}]}],
    }
    response = await harness.client.post("/v1/chat/completions", json=body, headers=AUTH)
    assert response.json()["mirrorguard"]["risk_level"] == "medium"


async def test_streaming_follows_the_openai_event_format(harness):
    response = await harness.client.post(
        "/v1/chat/completions", json=chat("I have not slept", stream=True), headers=AUTH
    )
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert events[-1] == "[DONE]"
    assert events[0]["choices"][0]["delta"] == {"role": "assistant", "content": ""}
    text = "".join(e["choices"][0]["delta"].get("content", "") for e in events[:-1])
    assert text == "sure thing "
    final = events[-2]
    assert final["choices"][0]["finish_reason"] == "stop"
    assert final["mirrorguard"]["action"] == "steer"
    assert all(e["object"] == "chat.completion.chunk" for e in events[:-1])


async def test_stream_reports_an_upstream_failure_inside_the_stream(tmp_path):
    def fail(messages):
        raise LLMError("provider exploded")

    h = await make_harness(tmp_path, respond=fail)
    response = await h.client.post(
        "/v1/chat/completions", json=chat("hi", stream=True), headers=AUTH
    )
    events = parse_sse(response.text)
    assert events[-1] == "[DONE]" and "provider exploded" in events[-2]["error"]["message"]
    await h.client.aclose()
    await h.services.stop()


@pytest.mark.parametrize(
    ("error", "status", "kind"),
    [(LLMError("bad"), 502, "upstream_error"), (RetryableLLMError("busy"), 503, "upstream_busy")],
)
async def test_upstream_failures_become_clear_errors(tmp_path, error, status, kind):
    def fail(messages):
        raise error

    h = await make_harness(tmp_path, respond=fail)
    response = await h.client.post("/v1/chat/completions", json=chat("hi"), headers=AUTH)
    assert response.status_code == status and response.json()["error"]["type"] == kind
    await h.client.aclose()
    await h.services.stop()


@pytest.mark.parametrize(
    "body",
    [
        {"model": "m", "messages": []},
        {"messages": [{"role": "user", "content": "hi"}]},
        {"model": "m", "messages": [{"role": "tool", "content": "hi"}]},
        {"model": "m", "messages": [{"role": "user", "content": "hi"}], "temperature": 9},
    ],
)
async def test_bad_requests_get_a_400_in_the_openai_error_shape(harness, body):
    response = await harness.client.post("/v1/chat/completions", json=body, headers=AUTH)
    assert response.status_code == 400
    assert set(response.json()["error"]) == {"message", "type", "code"}


async def test_model_not_on_the_allow_list_is_refused(tmp_path):
    h = await make_harness(tmp_path, policy=Policy(allowed_models=["only-this"]))
    response = await h.client.post("/v1/chat/completions", json=chat("hi"), headers=AUTH)
    assert response.status_code == 400 and "not allowed" in response.json()["error"]["message"]
    await h.client.aclose()
    await h.services.stop()


async def test_rate_limit_is_per_tenant(tmp_path):
    h = await make_harness(tmp_path, limit=2)
    codes = [
        (await h.client.post("/v1/chat/completions", json=chat("hi"), headers=AUTH)).status_code
        for _ in range(3)
    ]
    other = await h.client.post(
        "/v1/chat/completions", json=chat("hi"), headers={"Authorization": "Bearer key-two"}
    )
    assert codes == [200, 200, 429] and other.status_code == 200
    await h.client.aclose()
    await h.services.stop()


async def test_analyze_scores_without_calling_the_chatbot(harness):
    response = await harness.client.post(
        "/v1/analyze",
        json={"messages": [{"role": "user", "content": "I want to end it all"}]},
        headers=AUTH,
    )
    assert response.json() == {
        "risk_level": "high", "signals": ["self-harm"], "crisis": True, "from_fallback": False,
    }  # fmt: skip
    assert harness.upstream.calls == []


async def test_session_endpoint_shows_the_risk_timeline(harness):
    headers = {**AUTH, "X-Session-Id": "s1"}
    for text in ("hello", "I have not slept"):
        await harness.client.post("/v1/chat/completions", json=chat(text), headers=headers)
    await harness.services.sink.flush()
    body = (await harness.client.get("/v1/sessions/s1", headers=AUTH)).json()
    assert (body["turns"], body["risk_level"], body["recent_levels"]) == (2, "medium", [0, 1])
    assert [e["action"] for e in body["events"]] == ["pass", "steer"]
    assert body["events"][1]["signals"] == ["no sleep"]

    other = await harness.client.get("/v1/sessions/s1", headers={"Authorization": "Bearer key-two"})
    assert other.json()["turns"] == 0 and other.json()["events"] == []


# ---- small parts


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
