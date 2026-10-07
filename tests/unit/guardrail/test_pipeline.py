"""The guardrail pipeline, end to end with stand-ins."""

from mirrorguard.guardrail.events import MemorySink
from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.guardrail.policy import DEFAULT_CRISIS_MESSAGE, Policy, StaticPolicyStore
from mirrorguard.guardrail.types import Action, RiskLevel
from mirrorguard.llm.fake import FakeModel
from tests.support.fakes import KeywordScorer, StubReplyGuard, user

LOW, MEDIUM, HIGH = RiskLevel.LOW, RiskLevel.MEDIUM, RiskLevel.HIGH


def build(policy: Policy | None = None, **options):
    sink = MemorySink()
    guardrail = Guardrail(
        scorer=KeywordScorer(), policies=StaticPolicyStore(policy), events=sink, **options
    )
    return guardrail, sink, FakeModel("upstream", lambda messages: "sure thing")


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
