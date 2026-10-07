"""Settings read from environment variables (prefix MG_) and the .env file."""

from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MG_", env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///mirrorguard.db"
    redis_url: str | None = None

    # Model names use LiteLLM's "provider/model" form. Groq retires models from
    # time to time, so check these with `mirrorguard models check`.
    persona_model: str = "groq/openai/gpt-oss-20b"
    judge_model: str = "groq/openai/gpt-oss-120b"
    risk_model: str = "groq/openai/gpt-oss-20b"
    rewriter_model: str = "groq/openai/gpt-oss-120b"
    target_models: Annotated[list[str], NoDecode] = [
        "groq/openai/gpt-oss-120b",
        "groq/openai/gpt-oss-20b",
        "groq/llama-3.1-8b-instant",
    ]

    # Free tiers are tight. These limits are shared by every model call.
    llm_requests_per_minute: int = 25
    llm_max_concurrency: int = 4
    llm_max_retries: int = 6
    llm_timeout_seconds: float = 60.0

    benchmark_concurrency: int = 4

    # Extra admin API keys, as "key:tenant" pairs separated by commas. Handy for local
    # runs. In production, create keys with `mirrorguard keys create` instead.
    api_keys: str = ""
    tenant_requests_per_minute: int = 120
    session_ttl_seconds: int = 24 * 3600

    # Guardrail events older than this are removed by `mirrorguard retention purge`.
    retention_days: int = 90

    # Web addresses allowed to call the API from a browser (the dashboard).
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:3000"]

    @field_validator("target_models", "cors_origins", mode="before")
    @classmethod
    def _split_commas(cls, value):
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
