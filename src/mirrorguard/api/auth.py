"""Works out which tenant a request belongs to, from its API key."""

import hashlib
import hmac
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Tenant:
    id: str
    name: str = ""


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


class Authenticator(Protocol):
    async def authenticate(self, api_key: str) -> Tenant | None: ...


class StaticAuthenticator:
    """Keys from settings, written as "key:tenant,key:tenant". Only hashes are kept."""

    def __init__(self, pairs: str):
        self._tenants: dict[str, Tenant] = {}
        for pair in filter(None, (item.strip() for item in pairs.split(","))):
            key, _, tenant_id = pair.partition(":")
            if not key or not tenant_id:
                raise ValueError('API keys must be written as "key:tenant"')
            self._tenants[hash_key(key)] = Tenant(id=tenant_id, name=tenant_id)

    async def authenticate(self, api_key: str) -> Tenant | None:
        candidate = hash_key(api_key)
        found = None
        for stored, tenant in self._tenants.items():
            if hmac.compare_digest(stored, candidate):
                found = tenant
        return found
