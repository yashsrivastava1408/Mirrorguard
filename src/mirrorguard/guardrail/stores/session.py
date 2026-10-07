"""Remembers the recent risk level of each chat session."""

import json
from collections import OrderedDict
from dataclasses import asdict, dataclass, field
from typing import Protocol

from mirrorguard.guardrail.types import RiskLevel


@dataclass
class SessionState:
    levels: list[int] = field(default_factory=list)  # one entry per turn, newest last
    turns: int = 0
    crisis_seen: bool = False

    def record(self, level: RiskLevel, *, crisis: bool, keep: int) -> None:
        self.levels = [*self.levels, int(level)][-keep:]
        self.turns += 1
        self.crisis_seen = self.crisis_seen or crisis

    def level(self, window: int) -> RiskLevel:
        """The highest level seen in the last `window` turns."""
        recent = self.levels[-window:]
        return RiskLevel(max(recent)) if recent else RiskLevel.LOW


class SessionStore(Protocol):
    async def load(self, tenant_id: str, session_id: str) -> SessionState: ...

    async def save(self, tenant_id: str, session_id: str, state: SessionState) -> None: ...


class MemorySessionStore:
    """For one process only: tests and local runs. Forgets the oldest sessions when full."""

    def __init__(self, max_sessions: int = 10_000):
        self._states: OrderedDict[tuple[str, str], SessionState] = OrderedDict()
        self._max = max_sessions

    async def load(self, tenant_id: str, session_id: str) -> SessionState:
        state = self._states.get((tenant_id, session_id))
        return SessionState(**asdict(state)) if state else SessionState()

    async def save(self, tenant_id: str, session_id: str, state: SessionState) -> None:
        key = (tenant_id, session_id)
        self._states[key] = state
        self._states.move_to_end(key)
        while len(self._states) > self._max:
            self._states.popitem(last=False)


class RedisSessionStore:
    """Shared by every copy of the server, so any copy can handle any request."""

    def __init__(self, redis, *, ttl_seconds: int = 24 * 3600):
        self._redis = redis
        self._ttl = ttl_seconds

    @staticmethod
    def _key(tenant_id: str, session_id: str) -> str:
        return f"mg:session:{tenant_id}:{session_id}"

    async def load(self, tenant_id: str, session_id: str) -> SessionState:
        raw = await self._redis.get(self._key(tenant_id, session_id))
        return SessionState(**json.loads(raw)) if raw else SessionState()

    async def save(self, tenant_id: str, session_id: str, state: SessionState) -> None:
        await self._redis.set(
            self._key(tenant_id, session_id), json.dumps(asdict(state)), ex=self._ttl
        )
