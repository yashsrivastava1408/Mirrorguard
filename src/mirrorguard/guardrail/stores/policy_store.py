"""Tenant policies kept in the database, with a short-lived cache in front."""

import time
from collections.abc import Callable

from mirrorguard.db import Database
from mirrorguard.db.models import PolicyRecord
from mirrorguard.guardrail.policy import Policy


class DatabasePolicyStore:
    """Reads are cached for a few seconds, so a busy server does not ask the database
    for the policy on every chat message. A change reaches every server copy within
    `ttl_seconds`.
    """

    def __init__(
        self,
        database: Database,
        *,
        default: Policy | None = None,
        ttl_seconds: float = 15.0,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._db = database
        self._default = default or Policy()
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: dict[str, tuple[float, Policy]] = {}

    async def get(self, tenant_id: str) -> Policy:
        cached = self._cache.get(tenant_id)
        if cached and cached[0] > self._clock():
            return cached[1]
        async with self._db.session() as session:
            record = await session.get(PolicyRecord, tenant_id)
        policy = Policy.model_validate(record.data) if record else self._default
        self._cache[tenant_id] = (self._clock() + self._ttl, policy)
        return policy

    async def set(self, tenant_id: str, policy: Policy) -> None:
        async with self._db.session() as session, session.begin():
            record = await session.get(PolicyRecord, tenant_id)
            if record is None:
                session.add(PolicyRecord(tenant_id=tenant_id, data=policy.model_dump(mode="json")))
            else:
                record.data = policy.model_dump(mode="json")
        self._cache.pop(tenant_id, None)
