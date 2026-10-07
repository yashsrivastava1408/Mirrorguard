"""The FastAPI application."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mirrorguard.api.routes import admin, benchmarks, chat
from mirrorguard.api.services import Services
from mirrorguard.llm import LLMError, RetryableLLMError


def _error(status: int, message: str, kind: str) -> JSONResponse:
    """Errors use the OpenAI shape, so OpenAI client libraries show them properly."""
    return JSONResponse(
        {"error": {"message": message, "type": kind, "code": None}}, status_code=status
    )


def create_app(services: Services) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        await services.start()
        yield
        await services.stop()

    app = FastAPI(title="MirrorGuard", version="0.1.0", lifespan=lifespan)
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=services.settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Session-Id", "X-MirrorGuard-Risk", "X-MirrorGuard-Action"],
    )

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

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    app.include_router(chat.router)
    app.include_router(admin.router)
    app.include_router(benchmarks.router)
    return app


def app_from_settings() -> FastAPI:
    """Entry point for uvicorn: `uvicorn mirrorguard.api.app:app_from_settings --factory`."""
    from dotenv import load_dotenv

    from mirrorguard.api.services import build_services
    from mirrorguard.config import get_settings

    load_dotenv()
    return create_app(build_services(get_settings()))
