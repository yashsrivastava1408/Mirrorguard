"""The FastAPI application."""

import hashlib
import json
import time
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from mirrorguard.api.auth import Tenant
from mirrorguard.api.schemas import AnalyzeRequest, ChatRequest, GuardrailInfo
from mirrorguard.api.services import Services
from mirrorguard.guardrail.types import Decision, GuardedReply
from mirrorguard.llm import LLMError, RetryableLLMError


def _error(status: int, message: str, kind: str) -> JSONResponse:
    """Errors use the OpenAI shape, so OpenAI client libraries show them properly."""
    return JSONResponse(
        {"error": {"message": message, "type": kind, "code": None}}, status_code=status
    )


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


def create_app(services: Services) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await services.start()
        yield
        await services.stop()

    app = FastAPI(title="MirrorGuard", version="0.1.0", lifespan=lifespan)
    app.state.services = services

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return _error(exc.status_code, str(exc.detail), "invalid_request_error")

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        first = exc.errors()[0]
        where = ".".join(str(p) for p in first["loc"] if p != "body")
        return _error(400, f"{where}: {first['msg']}", "invalid_request_error")

    @app.exception_handler(RetryableLLMError)
    async def upstream_busy(request: Request, exc: RetryableLLMError):
        return _error(503, "The model provider is busy. Try again shortly.", "upstream_busy")

    @app.exception_handler(LLMError)
    async def upstream_failed(request: Request, exc: LLMError):
        return _error(502, f"The model provider returned an error: {exc}", "upstream_error")

    async def tenant(authorization: Annotated[str | None, Header()] = None) -> Tenant:
        scheme, _, key = (authorization or "").partition(" ")
        found = (
            await services.authenticator.authenticate(key.strip())
            if scheme.lower() == "bearer" and key.strip()
            else None
        )
        if found is None:
            raise HTTPException(401, "Missing or invalid API key.")
        if not await services.rate_limiter.allow(found.id):
            raise HTTPException(429, "Rate limit reached. Try again in a minute.")
        return found

    CurrentTenant = Annotated[Tenant, Depends(tenant)]

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.post("/v1/chat/completions")
    async def chat_completions(
        body: ChatRequest,
        current: CurrentTenant,
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

    @app.post("/v1/analyze")
    async def analyze(body: AnalyzeRequest, current: CurrentTenant):
        """Score a conversation without calling a chatbot and without touching any session."""
        messages = [m for m in ChatRequest(model="-", messages=body.messages).to_messages()]
        assessment = await services.guardrail.assess(current.id, messages)
        return {
            "risk_level": assessment.level.label,
            "signals": list(assessment.signals),
            "crisis": assessment.crisis,
            "from_fallback": assessment.from_fallback,
        }

    @app.get("/v1/sessions/{session_id}")
    async def session(session_id: str, current: CurrentTenant):
        policy = await services.guardrail.policy_for(current.id)
        state = await services.sessions.load(current.id, session_id)
        events = (
            await services.events.for_session(current.id, session_id) if services.events else []
        )
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

    return app


def app_from_settings() -> FastAPI:
    """Entry point for uvicorn: `uvicorn mirrorguard.api.app:app_from_settings --factory`."""
    from dotenv import load_dotenv

    from mirrorguard.api.services import build_services
    from mirrorguard.config import get_settings

    load_dotenv()
    return create_app(build_services(get_settings()))
