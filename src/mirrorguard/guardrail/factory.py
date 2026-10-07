"""Builds benchmark targets, with or without the guardrail in front."""

from mirrorguard.benchmark.types import Job
from mirrorguard.config import Settings
from mirrorguard.llm import ChatModel
from mirrorguard.llm.factory import ModelFactory


def build_target_factory(settings: Settings, models: ModelFactory):
    def target_for(job: Job) -> ChatModel:
        if job.guardrail:
            raise NotImplementedError("the guardrail arrives in Phase 4")
        return models(job.target_model)

    return target_for
