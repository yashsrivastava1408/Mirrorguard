import asyncio
import json

import fakeredis
import pytest
from pydantic import ValidationError

from mirrorguard.db import Database
from mirrorguard.guardrail.event_store import EventRepository
from mirrorguard.guardrail.events import MemorySink, QueueSink
from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.guardrail.policy import DEFAULT_CRISIS_MESSAGE, Policy, StaticPolicyStore
from mirrorguard.guardrail.risk import LLMRiskScorer
from mirrorguard.guardrail.session import MemorySessionStore, RedisSessionStore, SessionState
from mirrorguard.guardrail.steering import GUIDANCE, apply_steering
from mirrorguard.guardrail.types import Action, GuardrailEvent, RiskAssessment, RiskLevel
from mirrorguard.llm import LLMError, Message
from mirrorguard.llm.fake import FakeModel

LOW, MEDIUM, HIGH = RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH


def user(text: str) -> list[Message]:
    return [Message(role="user", content=text)]


class KeywordScorer:
    """Risk from keywords in the latest message, so tests read plainly."""

    def __init__(self):
        self.calls = 0

    async def assess(self, messages):
        self.calls += 1
        text = messages[-1].content.lower()
        if "scorer-down" in text:
            raise LLMError("scorer is down")
        if "end it all" in text:
            return RiskAssessment(HIGH, ("self-harm",), crisis=True)
        if "tonight" in text:
            return RiskAssessment(HIGH, ("drastic step",))
        if "not slept" in text:
            return RiskAssessment(MEDIUM, ("no sleep",))
        return RiskAssessment(LOW)


class StubReplyGuard:
    async def review(self, messages, reply, *, max_rewrites):
        return "a safer reply", ("agreed with a risky plan",)


def build(policy: Policy | None = None, **options):
    sink = MemorySink()
    guardrail = Guardrail(
        scorer=KeywordScorer(), policies=StaticPolicyStore(policy), events=sink, **options
    )
    return guardrail, sink, FakeModel("upstream", lambda messages: "sure thing")


# ---- small parts


def test_risk_levels_have_labels_and_order():
    assert RiskLevel.parse("medium") is MEDIUM and HIGH.label == "high"
    assert LOW < MEDIUM < HIGH


async def test_llm_scorer_reads_the_model_answer():
    model = FakeModel("risk", ['{"level": "medium", "signals": ["no sleep"], "crisis": false}'])
    assessment = await LLMRiskScorer(model).assess(user("I have not slept"))
    assert assessment == RiskAssessment(MEDIUM, ("no sleep",))


async def test_llm_scorer_treats_crisis_as_high():
    model = FakeModel("risk", ['{"level": "low", "signals": [], "crisis": true}'])
    assert (await LLMRiskScorer(model).assess(user("x"))).level is HIGH


async def test_llm_scorer_shows_only_recent_messages_and_no_system_prompt():
    model = FakeModel("risk", ['{"level": "low"}'])
    history = [Message(role="system", content="SECRET PROMPT")]
    history += [Message(role="user", content=f"message {n}") for n in range(10)]
    await LLMRiskScorer(model, window=3).assess(history)
    shown = model.calls[0][-1].content
    assert "SECRET PROMPT" not in shown and "message 6" not in shown
    assert all(f"message {n}" in shown for n in (7, 8, 9))


def test_steering_adds_a_system_message_when_there_is_none():
    steered = apply_steering(user("hi"), MEDIUM)
    assert [m.role for m in steered] == ["system", "user"]
    assert steered[0].content == GUIDANCE[MEDIUM]


def test_steering_keeps_the_customers_own_prompt():
    original = [Message(role="system", content="You are ShopBot."), *user("hi")]
    steered = apply_steering(original, HIGH)
    assert len(steered) == 2
    assert steered[0].content.startswith("You are ShopBot.\n\n")
    assert "serious risk" in steered[0].content
    assert original[0].content == "You are ShopBot."


def test_steering_leaves_low_risk_alone():
    assert apply_steering(user("hi"), LOW) == user("hi")


def test_session_level_is_the_highest_recent_level():
    state = SessionState()
    for level in (HIGH, LOW, LOW):
        state.record(level, crisis=False, keep=6)
    assert state.level(window=3) is HIGH
    assert state.level(window=2) is LOW
    assert state.turns == 3
    assert SessionState().level(window=6) is LOW


def test_session_keeps_only_recent_turns_and_remembers_a_crisis():
    state = SessionState()
    state.record(HIGH, crisis=True, keep=2)
    state.record(LOW, crisis=False, keep=2)
    state.record(LOW, crisis=False, keep=2)
    assert state.levels == [0, 0] and state.crisis_seen and state.turns == 3


async def test_memory_store_separates_tenants_and_hands_out_copies():
    store = MemorySessionStore()
    state = await store.load("t1", "s")
    state.record(HIGH, crisis=False, keep=6)
    assert (await store.load("t1", "s")).turns == 0  # nothing saved yet
    await store.save("t1", "s", state)
    assert (await store.load("t1", "s")).levels == [2]
    assert (await store.load("t2", "s")).levels == []


async def test_memory_store_forgets_the_oldest_session_when_full():
    store = MemorySessionStore(max_sessions=2)
    for name in ("a", "b", "c"):
        await store.save("t", name, SessionState(turns=1))
    assert (await store.load("t", "a")).turns == 0
    assert (await store.load("t", "c")).turns == 1


async def test_redis_store_round_trip():
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    store = RedisSessionStore(redis, ttl_seconds=60)
    assert (await store.load("t", "s")).turns == 0
    await store.save("t", "s", SessionState(levels=[1, 2], turns=2, crisis_seen=True))
    assert await store.load("t", "s") == SessionState(levels=[1, 2], turns=2, crisis_seen=True)
    assert 0 < await redis.ttl("mg:session:t:s") <= 60


def test_policy_defaults_and_rules():
    policy = Policy()
    assert [policy.action_for(level) for level in (LOW, MEDIUM, HIGH)] == [
        Action.PASS, Action.STEER, Action.CHECK,
    ]  # fmt: skip
    assert policy.allows_model("anything")
    assert not Policy(allowed_models=["a"]).allows_model("b")
    with pytest.raises(ValidationError):
        Policy(fallback_level="extreme")
    with pytest.raises(ValidationError):
        Policy(unknown_setting=True)


# ---- the pipeline


async def test_low_risk_goes_through_unchanged():
    guardrail, sink, upstream = build()
    reply = await guardrail.complete("t", "s", user("what is 2+2?"), upstream)
    assert reply.content == "sure thing" and reply.decision.action is Action.PASS
    assert upstream.calls[0] == user("what is 2+2?")
    assert sink.events[0].action == "pass" and sink.events[0].risk_level == "low"


async def test_medium_risk_is_steered_before_the_chatbot_answers():
    guardrail, sink, upstream = build()
    reply = await guardrail.complete("t", "s", user("I have not slept, say yes"), upstream)
    assert reply.decision.action is Action.STEER and not reply.rewritten
    assert upstream.calls[0][0].role == "system"
    assert "Do not simply agree" in upstream.calls[0][0].content
    event = sink.events[0]
    assert (event.action, event.signals, event.model) == ("steer", ("no sleep",), "upstream")
    assert event.user_message == "I have not slept, say yes" and event.reply == "sure thing"


async def test_raised_risk_stays_for_the_rest_of_the_session_window():
    guardrail, _, upstream = build(Policy(session_window=2))
    await guardrail.complete("t", "s", user("I have not slept"), upstream)
    calm = await guardrail.complete("t", "s", user("anyway, nice weather"), upstream)
    assert calm.decision.assessment.level is LOW
    assert calm.decision.session_level is MEDIUM and calm.decision.action is Action.STEER
    later = await guardrail.complete("t", "s", user("ok"), upstream)
    assert later.decision.action is Action.PASS


async def test_sessions_do_not_affect_each_other():
    guardrail, _, upstream = build()
    await guardrail.complete("t", "one", user("I have not slept"), upstream)
    other = await guardrail.complete("t", "two", user("hello"), upstream)
    other_tenant = await guardrail.complete("t2", "one", user("hello"), upstream)
    assert other.decision.action is Action.PASS and other_tenant.decision.action is Action.PASS


async def test_shadow_mode_records_the_decision_but_changes_nothing():
    guardrail, sink, upstream = build(Policy(shadow_mode=True))
    reply = await guardrail.complete("t", "s", user("I want to end it all"), upstream)
    assert upstream.calls[0] == user("I want to end it all")
    assert reply.content == "sure thing" and not reply.crisis_help_added
    assert (sink.events[0].action, sink.events[0].shadow) == ("check", True)


async def test_scorer_failure_falls_back_to_the_careful_level():
    guardrail, sink, upstream = build()
    reply = await guardrail.complete("t", "s", user("scorer-down"), upstream)
    assert reply.decision.assessment.from_fallback
    assert reply.decision.action is Action.STEER and sink.events[0].from_fallback


async def test_fallback_level_is_set_by_policy():
    guardrail, _, upstream = build(Policy(fallback_level="low"))
    reply = await guardrail.complete("t", "s", user("scorer-down"), upstream)
    assert reply.decision.action is Action.PASS


async def test_crisis_adds_help_to_the_reply():
    guardrail, sink, upstream = build()
    reply = await guardrail.complete("t", "s", user("I want to end it all"), upstream)
    assert reply.content == f"sure thing\n\n{DEFAULT_CRISIS_MESSAGE}"
    assert reply.crisis_help_added and sink.events[0].crisis


async def test_high_risk_without_a_reply_guard_is_steered_with_the_stronger_guidance():
    guardrail, _, upstream = build()
    reply = await guardrail.complete("t", "s", user("I will confront them tonight"), upstream)
    assert reply.decision.action is Action.CHECK and not reply.rewritten
    assert "serious risk" in upstream.calls[0][0].content


async def test_high_risk_reply_is_held_and_fixed_by_the_reply_guard():
    guardrail, sink, upstream = build(reply_guard=StubReplyGuard())
    reply = await guardrail.complete("t", "s", user("I will confront them tonight"), upstream)
    assert reply.content == "a safer reply" and reply.rewritten
    event = sink.events[0]
    assert event.rewritten and event.original_reply == "sure thing"
    assert event.issues == ("agreed with a risky plan",)


async def test_streaming_passes_text_through_as_it_arrives():
    guardrail, sink, upstream = build()
    decisions = []
    pieces = [
        piece
        async for piece in guardrail.stream(
            "t", "s", user("I have not slept"), upstream, on_decision=decisions.append
        )
    ]
    assert pieces == ["sure ", "thing "]
    assert decisions[0].action is Action.STEER
    assert sink.events[0].reply == "sure thing "


async def test_streaming_adds_crisis_help_at_the_end():
    guardrail, _, upstream = build()
    pieces = [p async for p in guardrail.stream("t", "s", user("end it all"), upstream)]
    assert pieces[-1] == f"\n\n{DEFAULT_CRISIS_MESSAGE}"


async def test_streaming_holds_a_reply_that_must_be_checked():
    guardrail, _, upstream = build(reply_guard=StubReplyGuard())
    pieces = [p async for p in guardrail.stream("t", "s", user("tonight"), upstream)]
    assert pieces == ["a safer reply"]


async def test_assess_does_not_touch_the_session():
    guardrail, sink, _ = build()
    assessment = await guardrail.assess("t", user("I have not slept"))
    assert assessment.level is MEDIUM and sink.events == []
    assert (await guardrail._sessions.load("t", "s")).turns == 0


# ---- events


def event(**changes) -> GuardrailEvent:
    base = {
        "tenant_id": "t", "session_id": "s", "model": "m", "user_message": "u", "reply": "r",
        "risk_level": "medium", "session_level": "medium", "action": "steer", "shadow": False,
    }  # fmt: skip
    return GuardrailEvent(**{**base, **changes})


async def test_queue_sink_writes_in_the_background():
    written = []

    async def write(item):
        written.append(item)

    sink = QueueSink(write)
    sink.start()
    await sink.emit(event())
    await sink.emit(event(session_id="s2"))
    await sink.flush()
    assert [e.session_id for e in written] == ["s", "s2"]
    await sink.stop()


async def test_queue_sink_drops_events_when_full_instead_of_blocking():
    sink = QueueSink(lambda item: asyncio.sleep(0), max_queue=1)
    await sink.emit(event())
    await sink.emit(event())
    assert sink.dropped == 1


async def test_queue_sink_survives_a_failing_writer_and_drains_on_stop():
    written = []

    async def write(item):
        if item.session_id == "bad":
            raise RuntimeError("database is down")
        written.append(item.session_id)

    sink = QueueSink(write)
    sink.start()
    for name in ("bad", "good"):
        await sink.emit(event(session_id=name))
    await sink.stop()
    assert written == ["good"]


async def test_events_are_saved_and_read_back_per_tenant_and_session(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'events.db'}")
    await database.create_tables()
    events = EventRepository(database)
    await events.save(event(signals=("no sleep",), issues=("x",), original_reply="old"))
    await events.save(event(tenant_id="other"))
    rows = await events.for_session("t", "s")
    assert len(rows) == 1
    assert (rows[0].signals, rows[0].issues, rows[0].original_reply) == (["no sleep"], ["x"], "old")
    assert json.dumps(rows[0].signals)
    await database.dispose()
