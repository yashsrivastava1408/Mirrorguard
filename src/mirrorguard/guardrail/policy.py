"""Each tenant's rules: what to do at each risk level."""

from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field

from mirrorguard.guardrail.types import Action, RiskLevel

DEFAULT_CRISIS_MESSAGE = (
    "If you are in immediate danger or thinking about harming yourself, please contact your "
    "local emergency number or a crisis helpline right now. In India you can call Tele-MANAS "
    "on 14416, free and open day and night. You do not have to face this alone."
)


class Policy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    low_action: Action = Action.PASS
    medium_action: Action = Action.STEER
    high_action: Action = Action.CHECK

    # Record what would have been done, but change nothing. For trying the guardrail safely.
    shadow_mode: bool = False

    # The level assumed when the risk scorer fails. Medium means "when unsure, take care".
    fallback_level: str = Field(default="medium", pattern="^(low|medium|high)$")

    # A raised risk level stays in force for this many turns.
    session_window: int = Field(default=6, ge=1, le=50)

    max_rewrites: int = Field(default=1, ge=0, le=3)
    crisis_message: str = DEFAULT_CRISIS_MESSAGE
    allowed_models: list[str] | None = None

    def action_for(self, level: RiskLevel) -> Action:
        return {
            RiskLevel.LOW: self.low_action,
            RiskLevel.MEDIUM: self.medium_action,
            RiskLevel.HIGH: self.high_action,
        }[level]

    def allows_model(self, model: str) -> bool:
        return self.allowed_models is None or model in self.allowed_models


class PolicyStore(Protocol):
    async def get(self, tenant_id: str) -> Policy: ...


class StaticPolicyStore:
    """The same policy for every tenant. Used until policies live in the database."""

    def __init__(self, policy: Policy | None = None):
        self._policy = policy or Policy()

    async def get(self, tenant_id: str) -> Policy:
        return self._policy
