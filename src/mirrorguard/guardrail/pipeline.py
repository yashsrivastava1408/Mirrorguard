"""The guardrail itself: score the risk, decide, steer, and (at high risk) check the reply."""

import logging
from collections.abc import AsyncIterator, Sequence
from typing import Protocol

from mirrorguard.guardrail.events import EventSink, NullSink
from mirrorguard.guardrail.policy import Policy, PolicyStore, StaticPolicyStore
from mirrorguard.guardrail.risk import RiskScorer
from mirrorguard.guardrail.session import MemorySessionStore, SessionStore
from mirrorguard.guardrail.steering import apply_steering
from mirrorguard.guardrail.types import (
    Action,
    Decision,
    GuardedReply,
    GuardrailEvent,
    RiskAssessment,
    RiskLevel,
)
from mirrorguard.llm import ChatModel, LLMError, Message

log = logging.getLogger(__name__)


class ReplyGuard(Protocol):
    """Checks a held reply and fixes it if needed. Arrives in Phase 6."""

    async def review(
        self, messages: Sequence[Message], reply: str, *, max_rewrites: int
    ) -> tuple[str, tuple[str, ...]]:
        """Return the reply to send and the problems found in the original."""
        ...


class Guardrail:
    def __init__(
        self,
        *,
        scorer: RiskScorer,
        sessions: SessionStore | None = None,
        policies: PolicyStore | None = None,
        events: EventSink | None = None,
        reply_guard: ReplyGuard | None = None,
    ):
        self._scorer = scorer
        self._sessions = sessions or MemorySessionStore()
        self._policies = policies or StaticPolicyStore()
        self._events = events or NullSink()
        self._reply_guard = reply_guard

    async def _assess(self, messages: Sequence[Message], policy: Policy) -> RiskAssessment:
        try:
            return await self._scorer.assess(messages)
        except LLMError as exc:
            log.warning("risk scorer failed, using the fallback level: %s", exc)
            return RiskAssessment(RiskLevel.parse(policy.fallback_level), from_fallback=True)

    async def policy_for(self, tenant_id: str) -> Policy:
        return await self._policies.get(tenant_id)

    async def assess(self, tenant_id: str, messages: Sequence[Message]) -> RiskAssessment:
        """Score a conversation without changing any session."""
        return await self._assess(messages, await self._policies.get(tenant_id))

    async def decide(
        self, tenant_id: str, session_id: str, messages: Sequence[Message]
    ) -> tuple[Decision, Policy]:
        """Score the latest message, update the session and choose the action."""
        policy = await self._policies.get(tenant_id)
        assessment = await self._assess(messages, policy)
        state = await self._sessions.load(tenant_id, session_id)
        state.record(assessment.level, crisis=assessment.crisis, keep=policy.session_window)
        await self._sessions.save(tenant_id, session_id, state)
        session_level = state.level(policy.session_window)
        decision = Decision(
            assessment=assessment,
            session_level=session_level,
            action=policy.action_for(session_level),
            shadow=policy.shadow_mode,
        )
        return decision, policy

    @staticmethod
    def outgoing(messages: Sequence[Message], decision: Decision) -> list[Message]:
        """The conversation as it should be sent to the chatbot."""
        if decision.applied_action is Action.PASS:
            return list(messages)
        return apply_steering(messages, decision.session_level)

    def _holds_reply(self, decision: Decision) -> bool:
        return decision.applied_action is Action.CHECK and self._reply_guard is not None

    async def _finish(
        self, messages: Sequence[Message], reply: str, decision: Decision, policy: Policy
    ) -> GuardedReply:
        """Check a held reply, and add crisis help when it is called for."""
        content, issues = reply, ()
        if self._holds_reply(decision):
            content, issues = await self._reply_guard.review(
                messages, reply, max_rewrites=policy.max_rewrites
            )
        rewritten = content != reply
        add_help = decision.assessment.crisis and not decision.shadow
        if add_help:
            content = f"{content}\n\n{policy.crisis_message}"
        return GuardedReply(
            content=content,
            decision=decision,
            rewritten=rewritten,
            issues=issues,
            crisis_help_added=add_help,
        )

    async def _record(
        self,
        tenant_id: str,
        session_id: str,
        model: str,
        messages: Sequence[Message],
        original: str,
        result: GuardedReply,
    ) -> None:
        decision = result.decision
        last_user = next((m.content for m in reversed(messages) if m.role == "user"), "")
        await self._events.emit(
            GuardrailEvent(
                tenant_id=tenant_id,
                session_id=session_id,
                model=model,
                user_message=last_user,
                reply=result.content,
                risk_level=decision.assessment.level.label,
                session_level=decision.session_level.label,
                action=decision.action.value,
                shadow=decision.shadow,
                signals=decision.assessment.signals,
                crisis=decision.assessment.crisis,
                rewritten=result.rewritten,
                issues=result.issues,
                original_reply=original if result.rewritten else None,
                from_fallback=decision.assessment.from_fallback,
            )
        )

    async def complete(
        self,
        tenant_id: str,
        session_id: str,
        messages: Sequence[Message],
        upstream: ChatModel,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> GuardedReply:
        decision, policy = await self.decide(tenant_id, session_id, messages)
        reply = await upstream.complete(
            self.outgoing(messages, decision), temperature=temperature, max_tokens=max_tokens
        )
        result = await self._finish(messages, reply, decision, policy)
        await self._record(tenant_id, session_id, upstream.name, messages, reply, result)
        return result

    async def stream(
        self,
        tenant_id: str,
        session_id: str,
        messages: Sequence[Message],
        upstream: ChatModel,
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        on_decision=None,
    ) -> AsyncIterator[str]:
        """Stream the reply. Only a reply that must be checked is held back first."""
        decision, policy = await self.decide(tenant_id, session_id, messages)
        if on_decision is not None:
            on_decision(decision)
        outgoing = self.outgoing(messages, decision)

        if self._holds_reply(decision):
            reply = await upstream.complete(
                outgoing, temperature=temperature, max_tokens=max_tokens
            )
            result = await self._finish(messages, reply, decision, policy)
            yield result.content
        else:
            pieces: list[str] = []
            async for piece in upstream.stream(
                outgoing, temperature=temperature, max_tokens=max_tokens
            ):
                pieces.append(piece)
                yield piece
            reply = "".join(pieces)
            result = await self._finish(messages, reply, decision, policy)
            if result.crisis_help_added:
                yield result.content[len(reply) :]
        await self._record(tenant_id, session_id, upstream.name, messages, reply, result)
