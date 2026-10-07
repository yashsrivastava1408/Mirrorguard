"""Endpoints behind the dashboard: numbers, flagged conversations, reviews and policy."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from mirrorguard.api.deps import ManageTenant, ReadTenant, ReviewTenant, ServicesDep
from mirrorguard.db.models import GuardrailEventRecord, ReviewRecord
from mirrorguard.guardrail.policy import Policy
from mirrorguard.tenancy.roles import Role

router = APIRouter(prefix="/v1", tags=["dashboard"])


class ReviewRequest(BaseModel):
    verdict: Literal["correct", "incorrect"]
    note: str = Field(default="", max_length=2000)
    reviewer: str = Field(default="", max_length=100)


def _event(event: GuardrailEventRecord, review: ReviewRecord | None) -> dict:
    return {
        "id": event.id,
        "at": event.created_at.isoformat(),
        "session_id": event.session_id,
        "model": event.model,
        "user_message": event.user_message,
        "reply": event.reply,
        "original_reply": event.original_reply,
        "risk_level": event.risk_level,
        "session_level": event.session_level,
        "action": event.action,
        "shadow": event.shadow,
        "crisis": event.crisis,
        "rewritten": event.rewritten,
        "from_fallback": event.from_fallback,
        "signals": event.signals,
        "issues": event.issues,
        "review": (
            {"verdict": review.verdict, "note": review.note, "reviewer": review.reviewer}
            if review
            else None
        ),
    }


@router.get("/stats")
async def stats(
    current: ReadTenant,
    services: ServicesDep,
    hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24,
):
    since = datetime.now(UTC) - timedelta(hours=hours)
    return {"hours": hours, **await services.events.stats(current.id, since)}


@router.get("/events")
async def events(
    current: ReadTenant,
    services: ServicesDep,
    risk_level: Literal["low", "medium", "high"] | None = None,
    unreviewed: bool = False,
    before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
):
    rows = await services.events.list(
        current.id, risk_level=risk_level, unreviewed_only=unreviewed, before=before, limit=limit
    )
    items = [_event(event, review) for event, review in rows]
    return {"events": items, "next_before": items[-1]["at"] if len(items) == limit else None}


@router.post("/events/{event_id}/review")
async def review(event_id: str, body: ReviewRequest, current: ReviewTenant, services: ServicesDep):
    saved = await services.events.add_review(
        current.id, event_id, verdict=body.verdict, note=body.note, reviewer=body.reviewer
    )
    if not saved:
        raise HTTPException(404, "No such event.")
    await services.audit.record(
        current.id, current.actor, "review.saved", target=event_id, detail={"verdict": body.verdict}
    )
    return {"status": "saved"}


@router.get("/policy")
async def get_policy(current: ReadTenant, services: ServicesDep):
    return (await services.guardrail.policy_for(current.id)).model_dump(mode="json")


@router.put("/policy")
async def put_policy(body: Policy, current: ManageTenant, services: ServicesDep):
    if services.policies is None:
        raise HTTPException(501, "Policies cannot be changed on this server.")
    before = await services.policies.get(current.id)
    await services.policies.set(current.id, body)
    changed = {
        field: {"from": old, "to": new}
        for field, new in body.model_dump(mode="json").items()
        if (old := before.model_dump(mode="json")[field]) != new
    }
    await services.audit.record(current.id, current.actor, "policy.changed", detail=changed)
    return body.model_dump(mode="json")


class NewKeyRequest(BaseModel):
    role: Role
    name: str = Field(default="", max_length=100)


@router.get("/keys")
async def list_keys(current: ManageTenant, services: ServicesDep):
    keys = await services.tenants.list_keys(current.id)
    return {
        "keys": [
            {
                "id": key.id,
                "name": key.name,
                "role": key.role,
                "starts_with": key.prefix,
                "created_at": key.created_at.isoformat(),
                "revoked": key.revoked_at is not None,
            }
            for key in keys
        ]
    }


@router.post("/keys", status_code=201)
async def create_key(body: NewKeyRequest, current: ManageTenant, services: ServicesDep):
    try:
        key_id, key = await services.tenants.create_key(current.id, role=body.role, name=body.name)
    except ValueError as exc:
        raise HTTPException(400, f"{exc}. Create the tenant first.") from exc
    await services.audit.record(
        current.id, current.actor, "key.created", target=key_id, detail={"role": body.role.value}
    )
    return {"id": key_id, "key": key, "note": "Store this key now. It is not shown again."}


@router.delete("/keys/{key_id}")
async def revoke_key(key_id: str, current: ManageTenant, services: ServicesDep):
    if not await services.tenants.revoke_key(current.id, key_id):
        raise HTTPException(404, "No such active key.")
    await services.audit.record(current.id, current.actor, "key.revoked", target=key_id)
    return {"status": "revoked"}


@router.get("/audit")
async def audit(
    current: ManageTenant,
    services: ServicesDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
):
    rows = await services.audit.list(current.id, limit=limit)
    return {
        "entries": [
            {
                "at": row.created_at.isoformat(),
                "actor": row.actor,
                "action": row.action,
                "target": row.target,
                "detail": row.detail,
            }
            for row in rows
        ]
    }
