"""The small guardrail parts: risk scorer, steering, sessions, policy."""

import fakeredis
import pytest
from pydantic import ValidationError

from mirrorguard.guardrail.policy import Policy
from mirrorguard.guardrail.risk import LLMRiskScorer
from mirrorguard.guardrail.steering import GUIDANCE, apply_steering
from mirrorguard.guardrail.stores.session import MemorySessionStore, RedisSessionStore, SessionState
from mirrorguard.guardrail.types import Action, RiskAssessment, RiskLevel
from mirrorguard.llm import Message
from mirrorguard.llm.fake import FakeModel
from tests.support.fakes import user

LOW, MEDIUM, HIGH = RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH


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
