"""Lets the benchmark test a chatbot with the guardrail in front of it."""

from collections.abc import AsyncIterator, Sequence

from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.llm import ChatModel, Message

BENCHMARK_TENANT = "benchmark"


class GuardedChatModel:
    """A chat model whose every reply passes through the guardrail.

    One instance serves one benchmark conversation, so each gets its own session.
    `trace` records what the guardrail did on each turn.
    """

    def __init__(self, upstream: ChatModel, guardrail: Guardrail, session_id: str):
        self.name = upstream.name
        self.trace: list[dict] = []
        self._upstream = upstream
        self._guardrail = guardrail
        self._session_id = session_id

    async def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str:
        reply = await self._guardrail.complete(
            BENCHMARK_TENANT,
            self._session_id,
            messages,
            self._upstream,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        decision = reply.decision
        self.trace.append(
            {
                "turn": len(self.trace) + 1,
                "risk_level": decision.assessment.level.label,
                "session_level": decision.session_level.label,
                "action": decision.action.value,
                "signals": list(decision.assessment.signals),
                "from_fallback": decision.assessment.from_fallback,
                "rewritten": reply.rewritten,
            }
        )
        return reply.content

    async def stream(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        yield await self.complete(messages, temperature=temperature, max_tokens=max_tokens)
