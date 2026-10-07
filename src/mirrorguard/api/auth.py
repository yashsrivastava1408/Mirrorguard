"""Works out which tenant a request belongs to, from its API key."""

import hmac
from collections.abc import Sequence
from typing import Protocol

from mirrorguard.tenancy.repository import Tenant, hash_key
from mirrorguard.tenancy.roles import Role

__all__ = ["Authenticator", "ChainAuthenticator", "StaticAuthenticator", "Tenant", "hash_key"]


class Authenticator(Protocol):
    async def authenticate(self, api_key: str) -> Tenant | None: ...


class StaticAuthenticator:
    """Admin keys from settings, written as "key:tenant,key:tenant". Only hashes are kept."""

    def __init__(self, pairs: str):
        self._tenants: dict[str, Tenant] = {}
        for pair in filter(None, (item.strip() for item in pairs.split(","))):
            key, _, tenant_id = pair.partition(":")
            if not key or not tenant_id:
                raise ValueError('API keys must be written as "key:tenant"')
            self._tenants[hash_key(key)] = Tenant(id=tenant_id, name=tenant_id, role=Role.ADMIN)

    async def authenticate(self, api_key: str) -> Tenant | None:
        candidate = hash_key(api_key)
        found = None
        for stored, tenant in self._tenants.items():
            if hmac.compare_digest(stored, candidate):
                found = tenant
        return found


class ChainAuthenticator:
    """Tries each authenticator in turn and returns the first match."""

    def __init__(self, authenticators: Sequence[Authenticator]):
        self._authenticators = list(authenticators)

    async def authenticate(self, api_key: str) -> Tenant | None:
        for authenticator in self._authenticators:
            tenant = await authenticator.authenticate(api_key)
            if tenant is not None:
                return tenant
        return None
