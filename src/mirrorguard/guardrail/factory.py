"""Builds the guardrail and the benchmark targets from settings."""

from uuid import uuid4

from mirrorguard.benchmark.types import Job
from mirrorguard.config import Settings
from mirrorguard.guardrail.benchmark_target import GuardedChatModel
from mirrorguard.guardrail.events import EventSink
from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.guardrail.policy import PolicyStore
from mirrorguard.guardrail.reply_guard import LLMReplyGuard
from mirrorguard.guardrail.risk import LLMRiskScorer
from mirrorguard.guardrail.session import SessionStore
from mirrorguard.llm import ChatModel
from mirrorguard.llm.factory import ModelFactory


def build_guardrail(
    settings: Settings,
    models: ModelFactory,
    *,
    sessions: SessionStore | None = None,
    policies: PolicyStore | None = None,
    events: EventSink | None = None,
) -> Guardrail:
    return Guardrail(
        scorer=LLMRiskScorer(models(settings.risk_model)),
        sessions=sessions,
        policies=policies,
        events=events,
        reply_guard=LLMReplyGuard(
            checker=models(settings.judge_model), rewriter=models(settings.rewriter_model)
        ),
    )


def build_target_factory(settings: Settings, models: ModelFactory):
    """Targets for the benchmark. Guardrail-on jobs share one guardrail, one session each."""
    guardrail = build_guardrail(settings, models)
    run_token = uuid4().hex[:8]

    def target_for(job: Job) -> ChatModel:
        upstream = models(job.target_model)
        if not job.guardrail:
            return upstream
        return GuardedChatModel(upstream, guardrail, session_id=f"{run_token}:{job.key}")

    return target_for
