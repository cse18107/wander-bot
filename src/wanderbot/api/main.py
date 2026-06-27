"""FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Response
from pydantic import BaseModel

from wanderbot import __version__
from wanderbot.config import get_settings
from wanderbot.observability.logging import configure_logging, get_logger

log = get_logger(__name__)


class HealthResponse(BaseModel):
    status: str
    version: str
    env: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_level)
    from wanderbot.observability.otel import setup_tracing

    setup_tracing(settings)
    from wanderbot.storage.db import init_db

    await init_db()
    log.info("startup", env=settings.env, version=__version__)
    yield
    log.info("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()
    # Ensure metric series are registered so /metrics always exposes them.
    import wanderbot.observability.metrics  # noqa: F401
    app = FastAPI(
        title="Wanderbot",
        version=__version__,
        description="Advanced multi-agent holiday planning system",
        lifespan=lifespan,
    )

    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["ops"])
    async def healthz() -> HealthResponse:
        return HealthResponse(status="ok", version=__version__, env=settings.env)

    @app.get("/metrics", tags=["ops"])
    async def metrics() -> Response:
        from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    for module, name in (
        ("wanderbot.api.auth_routes", "auth"),
        ("wanderbot.api.chat", "chat"),
        ("wanderbot.api.plan", "plan"),
        ("wanderbot.api.chat_threads", "chat_threads"),
        ("wanderbot.api.preferences", "preferences"),
    ):
        try:
            mod = __import__(module, fromlist=["router"])
            app.include_router(mod.router)
        except Exception as exc:  # pragma: no cover - resilience if optional deps missing
            log.warning("router_not_mounted", router=name, error=str(exc))

    return app


app = create_app()
