"""Tenants and API keys in a real database."""

import pytest

from mirrorguard.db import Database
from mirrorguard.tenancy.repository import DatabaseAuthenticator, TenantRepository
from mirrorguard.tenancy.roles import Role


@pytest.fixture
async def tenants(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 't.db'}")
    await database.create_tables()
    yield TenantRepository(database)
    await database.dispose()


async def test_keys_are_created_found_and_revoked(tenants):
    await tenants.create_tenant("acme", "Acme Ltd")
    with pytest.raises(ValueError, match="already exists"):
        await tenants.create_tenant("acme", "Again")
    with pytest.raises(ValueError, match="does not exist"):
        await tenants.create_key("ghost", role=Role.ADMIN)

    key_id, key = await tenants.create_key("acme", role=Role.REVIEWER, name="asha")
    assert key.startswith("mg_") and len(key) > 40
    found = await tenants.find_by_key(key)
    assert (found.id, found.name, found.role, found.key_id) == (
        "acme", "Acme Ltd", Role.REVIEWER, key_id,
    )  # fmt: skip
    assert found.actor == f"key:{key_id}"
    assert await tenants.find_by_key("mg_wrong") is None

    stored = (await tenants.list_keys("acme"))[0]
    assert key not in (stored.key_hash, stored.prefix) and stored.prefix == key[:10]

    await tenants.create_tenant("other", "Other")
    assert not await tenants.revoke_key("other", key_id)  # not their key
    assert await tenants.revoke_key("acme", key_id)
    assert not await tenants.revoke_key("acme", key_id)  # already revoked
    assert await tenants.find_by_key(key) is None


async def test_database_authenticator_caches_for_a_short_time(tenants):
    await tenants.create_tenant("acme", "Acme")
    key_id, key = await tenants.create_key("acme", role=Role.ADMIN)
    now = [0.0]
    auth = DatabaseAuthenticator(tenants, ttl_seconds=30, clock=lambda: now[0])
    assert (await auth.authenticate(key)).id == "acme"
    assert await auth.authenticate("not-a-mirrorguard-key") is None
    await tenants.revoke_key("acme", key_id)
    assert await auth.authenticate(key) is not None  # still cached
    now[0] = 31.0
    assert await auth.authenticate(key) is None
