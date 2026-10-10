"""FastAPI app factory. Run locally with `make dev` (uvicorn app.main:app --reload)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.log import configure_logging, get_logger
from app.models.schemas import HealthResponse

API_PREFIX = "/api/v1"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    settings.export_sdk_env()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=f"{settings.product_name} API",
        version="0.1.0",
        description=(
            f"{settings.product_name} checks the conversation behind a risky bank transfer. "
            "Gemini agents (ADK) extract evidence; a deterministic policy decides "
            "GREEN / AMBER / RED."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/healthz", response_model=HealthResponse, tags=["ops"])
    async def healthz() -> HealthResponse:
        # Dependency checks (Firestore, BigQuery, model) are added in phase 10.
        return HealthResponse(
            ok=True, model=settings.gemini_model, data_backend=settings.data_backend
        )

    get_logger(__name__).info(
        "app_started",
        product=settings.product_name,
        model=settings.gemini_model,
        data_backend=settings.data_backend,
        cloud=settings.is_cloud,
    )
    return app


app = create_app()
