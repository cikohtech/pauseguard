"""FastAPI app factory. Run locally with `make dev` (uvicorn app.main:app --reload).

Routes live in app/api/ under /api/v1 (docs/API_SPEC.md); OpenAPI is at /docs. Services
(repositories, orchestrator, evidence store) are built on the first request that needs them, or
passed in by tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import admin, cases, checks, health, metrics, personas, uploads, watchlist
from app.api.deps import Services
from app.api.errors import install_error_handlers
from app.config import Settings, get_settings
from app.log import configure_logging, get_logger
from app.telemetry import setup_tracing

API_PREFIX = "/api/v1"

TAGS = [
    {"name": "customer", "description": "The mobile banking app: checks, uploads, choices."},
    {"name": "analyst", "description": "The bank console (Firebase custom claim role=analyst)."},
    {"name": "ops", "description": "Health and admin (X-Admin-Token)."},
]


def create_app(settings: Settings | None = None, *, services: Services | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.export_sdk_env()
    configure_logging(settings.log_level)
    log = get_logger(__name__)
    tracing = setup_tracing(settings)  # Cloud Trace on Cloud Run (app/telemetry.py)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield
        # Cloud Run sends SIGTERM and waits 10 s: let running case files finish first.
        running: Services | None = getattr(app.state, "services", None)
        if running is not None:
            await running.drain()

    app = FastAPI(
        title=f"{settings.product_name} API",
        version="0.5.0",
        description=(
            f"{settings.product_name} checks the conversation behind a risky bank transfer. "
            "Gemini agents (ADK) extract evidence; a deterministic policy decides "
            "GREEN / AMBER / RED.\n\n"
            "**Auth:** customer routes take a Firebase ID token (anonymous sign-in is fine) as "
            "`Authorization: Bearer …`; `/cases*` and `/metrics` need the custom claim "
            "`role=analyst`; `/admin/*` needs `X-Admin-Token`. Errors always look like "
            '`{"error": {"code": "...", "message": "..."}}`. All data is synthetic.'
        ),
        openapi_tags=TAGS,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.services = services
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_error_handlers(app)
    for module in (checks, uploads, cases, metrics, watchlist, admin, personas):
        app.include_router(module.router, prefix=API_PREFIX)
    app.include_router(health.router)  # /health, outside /api/v1 (uptime checks, smoke)

    if settings.auth_disabled:
        log.warning("auth_disabled", note="local dev only: every request is a local analyst")
    log.info(
        "app_started",
        product=settings.product_name,
        model=settings.gemini_model,
        data_backend=settings.data_backend,
        uploads=settings.uploads,
        cloud=settings.is_cloud,
        cloud_trace=tracing,
    )
    return app


app = create_app()
