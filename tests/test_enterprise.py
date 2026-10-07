"""Tenants, keys, roles, the audit log, masking of personal details and retention."""

from datetime import UTC, datetime, timedelta

import pytest
from test_api import AUTH, chat, make_harness
from test_guardrail import event

from mirrorguard.cli import main
from mirrorguard.config import get_settings
from mirrorguard.db import Database
from mirrorguard.guardrail.event_store import NOT_STORED, EventRepository
from mirrorguard.privacy.redaction import PatternRedactor
from mirrorguard.tenancy.repository import DatabaseAuthenticator, TenantRepository
from mirrorguard.tenancy.roles import Permission, Role, allows

redact = PatternRedactor().redact


# ---- masking personal details


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mail me at asha.k+work@example.co.in please", "mail me at [EMAIL] please"),
        ("call +91 98765 43210 now", "call [PHONE] now"),
        ("my number is 9876543210", "my number is [PHONE]"),
        ("card 4111 1111 1111 1111 expires soon", "card [CARD] expires soon"),
        ("aadhaar 1234 5678 9012", "aadhaar [ID NUMBER]"),
        ("PAN ABCDE1234F", "PAN [ID NUMBER]"),
        ("see https://example.com/me?id=7 ok", "see [LINK] ok"),
        ("server 192.168.1.20 is down", "server [IP ADDRESS] is down"),
    ],
)
def test_personal_details_are_masked(text, expected):
    assert redact(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "I have not slept for 3 days and it is 2026 already",
        "I saved 150000 rupees over 12 months",
        "version 1.2.3 of the app",
        "I scored 87.5 percent",
    ],
)
def test_ordinary_numbers_are_left_alone(text):
    assert redact(text) == text


async def test_events_are_masked_before_they_are_stored(tmp_path):
    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'e.db'}")
    await database.create_tables()
    events = EventRepository(database, redactor=PatternRedactor())
    await events.save(
        event(user_message="I am at a@b.com", reply="ok a@b.com", original_reply="was a@b.com")
    )
    await events.save(event(session_id="private", user_message="secret", store_text=False))
    row = (await events.for_session("t", "s"))[0]
    assert (row.user_message, row.reply, row.original_reply) == (
        "I am at [EMAIL]", "ok [EMAIL]", "was [EMAIL]",
    )  # fmt: skip
    private = (await events.for_session("t", "private"))[0]
    assert (private.user_message, private.reply) == (NOT_STORED, NOT_STORED)
    assert private.original_reply is None and private.risk_level == "medium"
    await database.dispose()


async def test_old_events_are_purged_with_their_reviews(tmp_path):
    from sqlalchemy import func, select, update

    from mirrorguard.db.models import GuardrailEventRecord, ReviewRecord

    database = Database(f"sqlite+aiosqlite:///{tmp_path / 'r.db'}")
    await database.create_tables()
    events = EventRepository(database)
    for session_id in ("old", "new"):
        await events.save(event(session_id=session_id))
    old = (await events.for_session("t", "old"))[0]
    await events.add_review("t", old.id, verdict="correct", note="", reviewer="")
    async with database.session() as session, session.begin():
        await session.execute(
            update(GuardrailEventRecord)
            .where(GuardrailEventRecord.id == old.id)
            .values(created_at=datetime.now(UTC) - timedelta(days=100))
        )
    assert await events.purge_older_than(datetime.now(UTC) - timedelta(days=90)) == 1
    assert await events.for_session("t", "old") == []
    assert len(await events.for_session("t", "new")) == 1
    async with database.session() as session:
        assert await session.scalar(select(func.count()).select_from(ReviewRecord)) == 0
    await database.dispose()


# ---- roles


def test_role_permissions():
    table = {
        Role.ADMIN: {Permission.CHAT, Permission.READ, Permission.REVIEW, Permission.MANAGE},
        Role.ENGINEER: {Permission.CHAT, Permission.READ},
        Role.REVIEWER: {Permission.READ, Permission.REVIEW},
        Role.VIEWER: {Permission.READ},
    }
    for role, granted in table.items():
        assert {p for p in Permission if allows(role, p)} == granted


# ---- tenants and keys


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


# ---- the API with roles


@pytest.fixture
async def harness(tmp_path):
    h = await make_harness(tmp_path)
    await h.services.tenants.create_tenant("tenant-one", "Tenant One")
    yield h
    await h.client.aclose()
    await h.services.stop()


async def key_for(harness, role: str) -> dict:
    response = await harness.client.post(
        "/v1/keys", json={"role": role, "name": f"{role} key"}, headers=AUTH
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['key']}"}


async def flagged_event_id(harness) -> str:
    await harness.client.post("/v1/chat/completions", json=chat("I have not slept"), headers=AUTH)
    await harness.services.sink.flush()
    listed = await harness.client.get("/v1/events?risk_level=medium", headers=AUTH)
    return listed.json()["events"][0]["id"]


@pytest.mark.parametrize(
    ("role", "can_chat", "can_review", "can_manage"),
    [
        ("admin", True, True, True),
        ("engineer", True, False, False),
        ("reviewer", False, True, False),
        ("viewer", False, False, False),
    ],
)
async def test_each_role_can_do_only_what_it_should(
    harness, role, can_chat, can_review, can_manage
):
    event_id = await flagged_event_id(harness)
    headers = await key_for(harness, role)
    client = harness.client
    ok = lambda allowed: 200 if allowed else 403  # noqa: E731

    assert (await client.get("/v1/stats", headers=headers)).status_code == 200
    assert (await client.get("/v1/events", headers=headers)).status_code == 200
    posted = await client.post("/v1/chat/completions", json=chat("hi"), headers=headers)
    assert posted.status_code == ok(can_chat)
    reviewed = await client.post(
        f"/v1/events/{event_id}/review", json={"verdict": "correct"}, headers=headers
    )
    assert reviewed.status_code == ok(can_review)
    policy = (await client.get("/v1/policy", headers=headers)).json()
    assert (await client.put("/v1/policy", json=policy, headers=headers)).status_code == ok(
        can_manage
    )
    assert (await client.get("/v1/audit", headers=headers)).status_code == ok(can_manage)
    assert (await client.get("/v1/keys", headers=headers)).status_code == ok(can_manage)
    if not can_manage:
        refused = await client.get("/v1/keys", headers=headers)
        assert f"'{role}' role" in refused.json()["error"]["message"]


async def test_key_lifecycle_through_the_api(harness):
    client = harness.client
    created = await client.post("/v1/keys", json={"role": "viewer", "name": "tv"}, headers=AUTH)
    body = created.json()
    headers = {"Authorization": f"Bearer {body['key']}"}
    assert (await client.get("/v1/stats", headers=headers)).status_code == 200

    listed = (await client.get("/v1/keys", headers=AUTH)).json()["keys"]
    assert [(k["name"], k["role"], k["revoked"]) for k in listed] == [("tv", "viewer", False)]
    assert body["key"].startswith(listed[0]["starts_with"]) and "key" not in listed[0]

    assert (await client.delete(f"/v1/keys/{body['id']}", headers=AUTH)).status_code == 200
    assert (await client.get("/v1/stats", headers=headers)).status_code == 401
    assert (await client.delete(f"/v1/keys/{body['id']}", headers=AUTH)).status_code == 404
    bad_role = await client.post("/v1/keys", json={"role": "owner"}, headers=AUTH)
    assert bad_role.status_code == 400


async def test_keys_cannot_be_made_for_a_tenant_that_was_never_created(harness):
    response = await harness.client.post(
        "/v1/keys", json={"role": "viewer"}, headers={"Authorization": "Bearer key-two"}
    )
    assert response.status_code == 400 and "does not exist" in response.json()["error"]["message"]


async def test_changes_are_written_to_the_audit_log(harness):
    client = harness.client
    event_id = await flagged_event_id(harness)
    policy = (await client.get("/v1/policy", headers=AUTH)).json()
    await client.put("/v1/policy", json={**policy, "shadow_mode": True}, headers=AUTH)
    await client.post(f"/v1/events/{event_id}/review", json={"verdict": "incorrect"}, headers=AUTH)
    key = (await client.post("/v1/keys", json={"role": "viewer"}, headers=AUTH)).json()
    await client.delete(f"/v1/keys/{key['id']}", headers=AUTH)

    entries = (await client.get("/v1/audit", headers=AUTH)).json()["entries"]
    assert [e["action"] for e in entries] == [
        "key.revoked", "key.created", "review.saved", "policy.changed",
    ]  # fmt: skip
    changed = entries[-1]
    assert changed["detail"] == {"shadow_mode": {"from": False, "to": True}}
    assert changed["actor"] == "key:settings"
    assert entries[2]["target"] == event_id and entries[2]["detail"] == {"verdict": "incorrect"}

    other = await client.get("/v1/audit", headers={"Authorization": "Bearer key-two"})
    assert other.json()["entries"] == []


async def test_stored_text_is_masked_and_can_be_switched_off(harness):
    client = harness.client
    await client.post(
        "/v1/chat/completions",
        json=chat("I have not slept, reach me at me@example.com"),
        headers=AUTH,
    )
    await harness.services.sink.flush()
    stored = (await client.get("/v1/events", headers=AUTH)).json()["events"][0]
    assert stored["user_message"] == "I have not slept, reach me at [EMAIL]"
    assert (
        "me@example.com" in harness.upstream.calls[0][-1].content
    )  # the chatbot saw the real text

    policy = (await client.get("/v1/policy", headers=AUTH)).json()
    await client.put("/v1/policy", json={**policy, "store_text": False}, headers=AUTH)
    await client.post("/v1/chat/completions", json=chat("I have not slept again"), headers=AUTH)
    await harness.services.sink.flush()
    latest = (await client.get("/v1/events", headers=AUTH)).json()["events"][0]
    assert (latest["user_message"], latest["reply"]) == (NOT_STORED, NOT_STORED)
    assert latest["risk_level"] == "medium" and latest["signals"] == ["no sleep"]


# ---- command line


@pytest.fixture
def cli_database(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MG_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'cli.db'}")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_tenant_and_key_commands(cli_database, capsys):
    assert main(["tenants", "create", "acme", "--name", "Acme Ltd"]) == 0
    assert main(["tenants", "create", "acme"]) == 1
    assert "already exists" in capsys.readouterr().err
    assert main(["tenants", "list"]) == 0
    assert "Acme Ltd" in capsys.readouterr().out

    assert main(["keys", "create", "acme", "--role", "reviewer", "--name", "asha"]) == 0
    out = capsys.readouterr().out
    key_id = out.split("Key id : ")[1].split()[0]
    assert "API key: mg_" in out and "not shown again" in out
    assert main(["keys", "create", "ghost"]) == 1
    capsys.readouterr()

    assert main(["keys", "list", "acme"]) == 0
    listing = capsys.readouterr().out
    assert "reviewer" in listing and "active" in listing
    assert main(["keys", "revoke", "acme", key_id]) == 0
    assert main(["keys", "revoke", "acme", key_id]) == 1
    capsys.readouterr()
    assert main(["keys", "list", "acme"]) == 0
    assert "revoked" in capsys.readouterr().out


def test_retention_command(cli_database, capsys):
    assert main(["retention", "purge", "--days", "30"]) == 0
    assert "Removed 0 guardrail events older than 30 days" in capsys.readouterr().out
    assert main(["retention", "purge"]) == 0
    assert "older than 90 days" in capsys.readouterr().out
    assert main(["retention", "purge", "--days", "0"]) == 1
