"""Checking and rewriting held replies."""

from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.guardrail.policy import DEFAULT_CRISIS_MESSAGE, Policy, StaticPolicyStore
from mirrorguard.guardrail.reply_guard import LLMReplyGuard
from mirrorguard.llm import LLMError, Message
from mirrorguard.llm.fake import FakeModel
from tests.support.fakes import KeywordScorer

TALK = [
    Message(role="system", content="SECRET PROMPT"),
    Message(role="user", content="I will confront them tonight. I am right, yes?"),
]


OK = '{"ok": true, "issues": []}'


BAD = '{"ok": false, "issues": ["agrees with a risky plan"]}'


def down(messages):
    raise LLMError("model is down")


async def test_a_good_reply_is_sent_as_it_is():
    checker, rewriter = FakeModel("check", [OK]), FakeModel("rewrite", [])
    reply, issues = await LLMReplyGuard(checker, rewriter).review(TALK, "fine", max_rewrites=1)
    assert (reply, issues) == ("fine", ()) and rewriter.calls == []


async def test_a_bad_reply_is_rewritten_and_checked_again():
    checker, rewriter = FakeModel("check", [BAD, OK]), FakeModel("rewrite", ["  better  "])
    reply, issues = await LLMReplyGuard(checker, rewriter).review(TALK, "Yes, go!", max_rewrites=1)
    assert (reply, issues) == ("better", ("agrees with a risky plan",))
    assert len(checker.calls) == 2
    asked = rewriter.calls[0][-1].content
    assert "Yes, go!" in asked and "agrees with a risky plan" in asked
    assert "SECRET PROMPT" not in asked and "confront them tonight" in asked


async def test_rewriting_stops_at_the_limit():
    checker = FakeModel("check", [BAD, BAD, BAD])
    rewriter = FakeModel("rewrite", ["try one", "try two"])
    reply, issues = await LLMReplyGuard(checker, rewriter).review(TALK, "bad", max_rewrites=2)
    assert reply == "try two" and issues == ("agrees with a risky plan",)
    assert len(rewriter.calls) == 2 and len(checker.calls) == 3


async def test_no_rewrites_allowed_means_check_only():
    checker, rewriter = FakeModel("check", [BAD]), FakeModel("rewrite", [])
    reply, issues = await LLMReplyGuard(checker, rewriter).review(TALK, "bad", max_rewrites=0)
    assert reply == "bad" and issues == ("agrees with a risky plan",)


async def test_a_failed_verdict_without_reasons_still_counts_as_failed():
    checker = FakeModel("check", ['{"ok": false}', OK])
    rewriter = FakeModel("rewrite", ["better"])
    reply, issues = await LLMReplyGuard(checker, rewriter).review(TALK, "bad", max_rewrites=1)
    assert reply == "better" and issues == ("failed the safety check",)


async def test_an_empty_rewrite_keeps_the_previous_reply():
    checker, rewriter = FakeModel("check", [BAD, OK]), FakeModel("rewrite", ["   "])
    reply, _ = await LLMReplyGuard(checker, rewriter).review(TALK, "original", max_rewrites=1)
    assert reply == "original"


async def test_a_broken_checker_does_not_block_the_user():
    guard = LLMReplyGuard(FakeModel("check", down), FakeModel("rewrite", []))
    assert await guard.review(TALK, "original", max_rewrites=1) == ("original", ())


async def test_a_broken_rewriter_does_not_block_the_user():
    guard = LLMReplyGuard(FakeModel("check", [BAD]), FakeModel("rewrite", down))
    assert await guard.review(TALK, "original", max_rewrites=1) == ("original", ())


async def test_whole_flow_at_high_risk_with_a_crisis():
    """Steer, hold, check, rewrite, then add crisis help, in that order."""
    guard = LLMReplyGuard(FakeModel("check", [BAD, OK]), FakeModel("rewrite", ["a kind reply"]))
    guardrail = Guardrail(scorer=KeywordScorer(), reply_guard=guard)
    upstream = FakeModel("up", ["You are right, do it."])
    result = await guardrail.complete(
        "t", "s", [Message(role="user", content="I want to end it all")], upstream
    )
    assert "serious risk" in upstream.calls[0][0].content
    assert result.content == f"a kind reply\n\n{DEFAULT_CRISIS_MESSAGE}"
    assert result.rewritten and result.crisis_help_added
    assert result.issues == ("agrees with a risky plan",)


async def test_medium_risk_replies_are_never_held():
    checker = FakeModel("check", [])
    guard = LLMReplyGuard(checker, FakeModel("rewrite", []))
    guardrail = Guardrail(scorer=KeywordScorer(), reply_guard=guard)
    upstream = FakeModel("up", ["ok"])
    result = await guardrail.complete(
        "t", "s", [Message(role="user", content="I have not slept")], upstream
    )
    assert result.content == "ok" and checker.calls == []


async def test_policy_can_turn_rewriting_off():
    guard = LLMReplyGuard(FakeModel("check", [BAD]), FakeModel("rewrite", []))
    guardrail = Guardrail(
        scorer=KeywordScorer(),
        reply_guard=guard,
        policies=StaticPolicyStore(Policy(max_rewrites=0)),
    )
    result = await guardrail.complete(
        "t", "s", [Message(role="user", content="tonight")], FakeModel("up", ["risky"])
    )
    assert result.content == "risky" and not result.rewritten
    assert result.issues == ("agrees with a risky plan",)
