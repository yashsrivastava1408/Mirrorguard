"""Builds ready-to-use models from settings. All of them share one Throttle."""

from collections.abc import Callable

from mirrorguard.config import Settings
from mirrorguard.llm.base import ChatModel
from mirrorguard.llm.litellm_model import LiteLLMModel
from mirrorguard.llm.resilient import ResilientModel, Throttle

ModelFactory = Callable[[str], ChatModel]


def make_model_factory(settings: Settings) -> ModelFactory:
    throttle = Throttle(
        requests_per_minute=settings.llm_requests_per_minute,
        max_concurrency=settings.llm_max_concurrency,
    )
    cache: dict[str, ChatModel] = {}

    def build(name: str) -> ChatModel:
        if name not in cache:
            cache[name] = ResilientModel(
                LiteLLMModel(name, timeout=settings.llm_timeout_seconds),
                throttle,
                max_retries=settings.llm_max_retries,
            )
        return cache[name]

    return build
