"""Roles, API keys and the audit log through the API."""

import pytest

from mirrorguard.guardrail.stores.event_store import NOT_STORED
from tests.support.api import AUTH, chat, make_harness


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
