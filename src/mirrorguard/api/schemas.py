"""Request and response shapes. The chat ones follow the OpenAI chat completions format."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from mirrorguard.llm import Message


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

    @field_validator("content", mode="before")
    @classmethod
    def _join_text_parts(cls, value):
        # OpenAI clients may send content as a list of parts. Only text parts are supported.
        if isinstance(value, list):
            return "".join(
                part.get("text", "")
                for part in value
                if isinstance(part, dict) and part.get("type") == "text"
            )
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    stream: bool = False
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1)
    user: str | None = None

    def to_messages(self) -> list[Message]:
        return [Message(role=m.role, content=m.content) for m in self.messages]


class AnalyzeRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1)


class GuardrailInfo(BaseModel):
    """What the guardrail did, returned next to the normal OpenAI fields."""

    risk_level: str
    session_level: str
    action: str
    shadow: bool
    signals: list[str]
    rewritten: bool = False
    crisis_help_added: bool = False
