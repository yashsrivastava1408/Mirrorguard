"""Builds the guardrail and the benchmark targets from settings."""

from mirrorguard.benchmark.types import Job
from mirrorguard.config import Settings
from mirrorguard.guardrail.events import EventSink
from mirrorguard.guardrail.pipeline import Guardrail
from mirrorguard.guardrail.policy import PolicyStore
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
    )


def build_target_factory(settings: Settings, models: ModelFactory):
    def target_for(job: Job) -> ChatModel:
        if job.guardrail:
            raise NotImplementedError("benchmarking with the guardrail on arrives in Phase 5")
        return models(job.target_model)

    return target_for
