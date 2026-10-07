"""The guarded chat endpoint and the endpoints next to it."""

import hashlib
import json
import time
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse

from mirrorguard.api.auth import Tenant
from mirrorguard.api.deps import ChatTenant, ReadTenant, ServicesDep
from mirrorguard.api.schemas import AnalyzeRequest, ChatRequest, GuardrailInfo
from mirrorguard.guardrail.types import Decision, GuardedReply
from mirrorguard.llm import LLMError

router = APIRouter(prefix="/v1", tags=["chat"])


def _info(decision: Decision, reply: GuardedReply | None = None) -> GuardrailInfo:
    return GuardrailInfo(
        risk_level=decision.assessment.level.label,
        session_level=decision.session_level.label,
        action=decision.action.value,
        shadow=decision.shadow,
        signals=list(decision.assessment.signals),
        rewritten=bool(reply and reply.rewritten),
        crisis_help_added=bool(reply and reply.crisis_help_added),
    )


def _session_id(tenant: Tenant, body: ChatRequest, header: str | None) -> str:
    """Use the caller's session id, else derive a stable one from the first user message."""
    if header or body.user:
        return header or body.user
    first = next((m.content for m in body.messages if m.role == "user"), "")
    return hashlib.sha256(f"{tenant.id}:{first}".encode()).hexdigest()[:32]


@router.post("/chat/completions")
async def chat_completions(
    body: ChatRequest,
    current: ChatTenant,
    services: ServicesDep,
    x_session_id: Annotated[str | None, Header()] = None,
):
    policy = await services.guardrail.policy_for(current.id)
    if not policy.allows_model(body.model):
        raise HTTPException(400, f"Model '{body.model}' is not allowed for this account.")
    session_id = _session_id(current, body, x_session_id)
    upstream = services.models(body.model)
    messages = body.to_messages()
    completion_id, created = f"chatcmpl-{uuid4().hex}", int(time.time())
    options = {"temperature": body.temperature, "max_tokens": body.max_tokens}

    if not body.stream:
        reply = await services.guardrail.complete(
            current.id, session_id, messages, upstream, **options
        )
        info = _info(reply.decision, reply)
        return JSONResponse(
            {
                "id": completion_id,
                "object": "chat.completion",
                "created": created,
                "model": body.model,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": reply.content},
                        "finish_reason": "stop",
                    }
                ],
                "mirrorguard": info.model_dump(),
            },
            headers={
                "X-MirrorGuard-Risk": info.session_level,
                "X-MirrorGuard-Action": info.action,
                "X-Session-Id": session_id,
            },
        )

    def chunk(delta: dict, finish: str | None = None, **extra) -> str:
        payload = {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": body.model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
            **extra,
        }
        return f"data: {json.dumps(payload)}\n\n"

    async def events():
        decided: list[Decision] = []
        try:
            yield chunk({"role": "assistant", "content": ""})
            async for piece in services.guardrail.stream(
                current.id,
                session_id,
                messages,
                upstream,
                on_decision=decided.append,
                **options,
            ):
                yield chunk({"content": piece})
            yield chunk({}, "stop", mirrorguard=_info(decided[0]).model_dump())
        except LLMError as exc:
            error = {"message": str(exc), "type": "upstream_error", "code": None}
            yield f"data: {json.dumps({'error': error})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        events(), media_type="text/event-stream", headers={"X-Session-Id": session_id}
    )


@router.post("/analyze")
async def analyze(body: AnalyzeRequest, current: ChatTenant, services: ServicesDep):
    """Score a conversation without calling a chatbot and without touching any session."""
    messages = [m for m in ChatRequest(model="-", messages=body.messages).to_messages()]
    assessment = await services.guardrail.assess(current.id, messages)
    return {
        "risk_level": assessment.level.label,
        "signals": list(assessment.signals),
        "crisis": assessment.crisis,
        "from_fallback": assessment.from_fallback,
    }


@router.get("/sessions/{session_id}")
async def session(session_id: str, current: ReadTenant, services: ServicesDep):
    policy = await services.guardrail.policy_for(current.id)
    state = await services.sessions.load(current.id, session_id)
    events = await services.events.for_session(current.id, session_id) if services.events else []
    return {
        "session_id": session_id,
        "turns": state.turns,
        "risk_level": state.level(policy.session_window).label,
        "recent_levels": state.levels,
        "crisis_seen": state.crisis_seen,
        "events": [
            {
                "at": e.created_at.isoformat(),
                "risk_level": e.risk_level,
                "session_level": e.session_level,
                "action": e.action,
                "signals": e.signals,
                "rewritten": e.rewritten,
            }
            for e in events
        ],
    }
