"""Endpoints behind the dashboard: numbers, flagged conversations, reviews and policy."""

from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from mirrorguard.api.deps import ServicesDep, TenantDep
from mirrorguard.db.models import GuardrailEventRecord, ReviewRecord
from mirrorguard.guardrail.policy import Policy

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
    current: TenantDep,
    services: ServicesDep,
    hours: Annotated[int, Query(ge=1, le=24 * 90)] = 24,
):
    since = datetime.now(UTC) - timedelta(hours=hours)
    return {"hours": hours, **await services.events.stats(current.id, since)}


@router.get("/events")
async def events(
    current: TenantDep,
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
async def review(event_id: str, body: ReviewRequest, current: TenantDep, services: ServicesDep):
    saved = await services.events.add_review(
        current.id, event_id, verdict=body.verdict, note=body.note, reviewer=body.reviewer
    )
    if not saved:
        raise HTTPException(404, "No such event.")
    return {"status": "saved"}


@router.get("/policy")
async def get_policy(current: TenantDep, services: ServicesDep):
    return (await services.guardrail.policy_for(current.id)).model_dump(mode="json")


@router.put("/policy")
async def put_policy(body: Policy, current: TenantDep, services: ServicesDep):
    if services.policies is None:
        raise HTTPException(501, "Policies cannot be changed on this server.")
    await services.policies.set(current.id, body)
    return body.model_dump(mode="json")
