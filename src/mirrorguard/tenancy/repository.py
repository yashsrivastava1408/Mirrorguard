"""Tenants and API keys in the database."""

import hashlib
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import select

from mirrorguard.db import Database
from mirrorguard.db.models import ApiKeyRecord, TenantRecord, now
from mirrorguard.tenancy.roles import Role

KEY_PREFIX = "mg_"


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str = ""
    role: Role = Role.ADMIN
    key_id: str = ""

    @property
    def actor(self) -> str:
        """How this caller is named in the audit log."""
        return f"key:{self.key_id}" if self.key_id else "key:settings"


class TenantRepository:
    def __init__(self, database: Database):
        self._db = database

    async def create_tenant(self, tenant_id: str, name: str) -> None:
        async with self._db.session() as session, session.begin():
            if await session.get(TenantRecord, tenant_id):
                raise ValueError(f"tenant '{tenant_id}' already exists")
            session.add(TenantRecord(id=tenant_id, name=name))

    async def list_tenants(self) -> list[TenantRecord]:
        async with self._db.session() as session:
            return list(await session.scalars(select(TenantRecord).order_by(TenantRecord.id)))

    async def create_key(self, tenant_id: str, *, role: Role, name: str = "") -> tuple[str, str]:
        """Make a new key. Returns (key id, the key itself). The key is shown only once."""
        key = KEY_PREFIX + secrets.token_urlsafe(32)
        async with self._db.session() as session, session.begin():
            if not await session.get(TenantRecord, tenant_id):
                raise ValueError(f"tenant '{tenant_id}' does not exist")
            record = ApiKeyRecord(
                tenant_id=tenant_id,
                key_hash=hash_key(key),
                prefix=key[:10],
                name=name,
                role=role.value,
            )
            session.add(record)
            await session.flush()
            return record.id, key

    async def list_keys(self, tenant_id: str) -> list[ApiKeyRecord]:
        async with self._db.session() as session:
            rows = await session.scalars(
                select(ApiKeyRecord)
                .where(ApiKeyRecord.tenant_id == tenant_id)
                .order_by(ApiKeyRecord.created_at)
            )
            return list(rows)

    async def revoke_key(self, tenant_id: str, key_id: str) -> bool:
        async with self._db.session() as session, session.begin():
            record = await session.get(ApiKeyRecord, key_id)
            if record is None or record.tenant_id != tenant_id or record.revoked_at:
                return False
            record.revoked_at = now()
            return True

    async def find_by_key(self, key: str) -> Tenant | None:
        async with self._db.session() as session:
            row = (
                await session.execute(
                    select(ApiKeyRecord, TenantRecord)
                    .join(TenantRecord, TenantRecord.id == ApiKeyRecord.tenant_id)
                    .where(
                        ApiKeyRecord.key_hash == hash_key(key), ApiKeyRecord.revoked_at.is_(None)
                    )
                )
            ).first()
        if row is None:
            return None
        record, tenant = row
        return Tenant(id=tenant.id, name=tenant.name, role=Role(record.role), key_id=record.id)


class DatabaseAuthenticator:
    """Looks keys up in the database, remembering each answer for a short time.

    The cache means a busy server does not query the database on every request.
    A revoked key stops working on every server copy within `ttl_seconds`.
    """

    def __init__(
        self,
        tenants: TenantRepository,
        *,
        ttl_seconds: float = 30.0,
        max_entries: int = 10_000,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._tenants = tenants
        self._ttl = ttl_seconds
        self._max = max_entries
        self._clock = clock
        self._cache: dict[str, tuple[float, Tenant | None]] = {}

    async def authenticate(self, api_key: str) -> Tenant | None:
        if not api_key.startswith(KEY_PREFIX):
            return None
        digest = hash_key(api_key)
        cached = self._cache.get(digest)
        if cached and cached[0] > self._clock():
            return cached[1]
        tenant = await self._tenants.find_by_key(api_key)
        if len(self._cache) >= self._max:
            self._cache.clear()
        self._cache[digest] = (self._clock() + self._ttl, tenant)
        return tenant

    def forget(self) -> None:
        self._cache.clear()
