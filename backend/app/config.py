"""Every environment variable the API reads, in one place (pydantic-settings).

Local dev reads `.env` from the repo root (and `backend/.env` if present).
Cloud Run gets the same names via `--set-env-vars` / `--set-secrets`.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
EMULATOR_PROJECT = "demo-pauseguard"  # offline project ID used by the local Firebase emulators


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Product. The name lives here only, so it can be changed in one place.
    product_name: str = "PauseGuard"

    # Google Cloud / Vertex AI
    google_cloud_project: str = "your-project-id"
    google_cloud_location: str = "global"  # Vertex AI location for Gemini
    google_genai_use_vertexai: bool = True
    gemini_model: str = "gemini-3.8-flash"  # never hard-code a model ID anywhere else
    gemini_thinking_level: Literal["LOW", "MEDIUM", "HIGH"] = "LOW"  # 3.8 Flash rejects MINIMAL
    # Images and PDF pages sent to the evidence agent (fewer input tokens than the default).
    gemini_media_resolution: Literal["LOW", "MEDIUM", "HIGH", "DEFAULT"] = "MEDIUM"
    data_region: str = "asia-southeast1"

    # Data
    data_backend: Literal["sqlite", "bigquery"] = "sqlite"
    sqlite_path: Path = Path("./data/seed/pauseguard.db")
    bq_dataset: str = "pauseguard"
    state_backend: Literal["firestore", "memory"] = "firestore"  # memory: tests, no emulator
    firestore_emulator_host: str | None = None
    evidence_bucket: str = "your-project-pauseguard-evidence"
    # Evidence uploads: gcs = signed URLs on EVIDENCE_BUCKET; local = files in LOCAL_UPLOADS_DIR
    # behind the API's own signed URLs. Unset: gcs on Cloud Run, local elsewhere.
    upload_backend: Literal["local", "gcs"] | None = None
    local_uploads_dir: Path = Path("./.local_uploads")  # relative to the repo root

    # API
    allowed_origins: str = "http://localhost:5173"  # comma-separated
    agent_timeout_seconds: float = 12.0  # customer-facing budget: evidence + intel + explainer
    explainer_budget_seconds: float = 4.0  # slower than this: the reviewed static message
    casefile_timeout_seconds: float = 25.0  # analyst-facing: case file ∥ web search, after `done`
    intel_max_searches: int = 2  # Google Search calls per check (AGENTS_SPEC §3)
    # No evidence answer after this many seconds: send the request again, first answer wins.
    evidence_hedge_after_seconds: float = 6.0  # 0 = off
    auth_disabled: bool = False
    firebase_auth_emulator_host: str | None = None  # local: verify Auth-emulator ID tokens
    admin_reset_token: str | None = None  # from Secret Manager in cloud
    rate_limit_checks: str = "30/hour"  # POST /checks per client IP
    rate_limit_checks_per_customer: str = "120/hour"  # per customer_id (judges share personas)
    log_level: str = "INFO"
    # Gemini prices for /metrics cost per check (USD per 1M tokens). Filled in by hand from the
    # published price list (phase 09, eval/pricing.yaml); unset: cost_per_check_usd is null.
    gemini_price_in_usd_per_mtok: float | None = None
    gemini_price_out_usd_per_mtok: float | None = None

    # Fusion policy thresholds (AGENTS_SPEC §4). Frozen before the test split is run.
    fusion_red_confidence: float = 0.75
    fusion_red_high_flags: int = 2
    fusion_red_txn_score: int = 50
    fusion_amber_confidence: float = 0.5
    fusion_amber_txn_score_no_evidence: int = 70
    # Proportionality (DECISIONS 2026-10-11): a scam pattern with no hard-stop signal holds the
    # payment only from this amount (SGD); below it the verdict is AMBER (cool-off). 0 = off.
    fusion_red_min_amount: float = 1000.0
    txn_green_fast_path_below: int = 30

    # Set by Cloud Run itself; used to detect "running in cloud".
    k_service: str | None = Field(default=None, alias="K_SERVICE")

    @model_validator(mode="after")
    def _resolve_and_guard(self) -> Settings:
        if not self.sqlite_path.is_absolute():
            self.sqlite_path = (REPO_ROOT / self.sqlite_path).resolve()
        if not self.local_uploads_dir.is_absolute():
            self.local_uploads_dir = (REPO_ROOT / self.local_uploads_dir).resolve()
        if self.k_service and self.auth_disabled:
            raise ValueError("AUTH_DISABLED=true is not allowed on Cloud Run (K_SERVICE is set).")
        if self.k_service and self.upload_backend == "local":
            raise ValueError("UPLOAD_BACKEND=local is not allowed on Cloud Run (K_SERVICE is set).")
        return self

    @property
    def is_cloud(self) -> bool:
        return self.k_service is not None

    @property
    def uploads(self) -> Literal["local", "gcs"]:
        return self.upload_backend or ("gcs" if self.is_cloud else "local")

    @property
    def uses_firestore_emulator(self) -> bool:
        return bool(self.firestore_emulator_host) and not self.is_cloud

    @property
    def firestore_project(self) -> str:
        """The emulators run as the offline `demo-pauseguard` project, whatever .env says."""
        return EMULATOR_PROJECT if self.uses_firestore_emulator else self.google_cloud_project

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    def export_sdk_env(self) -> None:
        """google-genai and the Firestore client read these from os.environ, not from Settings."""
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", self.google_cloud_project)
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", self.google_cloud_location)
        use_vertex = "TRUE" if self.google_genai_use_vertexai else "FALSE"
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", use_vertex)
        # google-genai 2.29 / ADK 2.11 renamed it; set both to the same value (no warning).
        os.environ.setdefault(
            "GOOGLE_GENAI_USE_ENTERPRISE", os.environ["GOOGLE_GENAI_USE_VERTEXAI"]
        )
        if self.uses_firestore_emulator and self.firestore_emulator_host:
            os.environ.setdefault("FIRESTORE_EMULATOR_HOST", self.firestore_emulator_host)
        if self.firebase_auth_emulator_host and not self.is_cloud:
            os.environ.setdefault("FIREBASE_AUTH_EMULATOR_HOST", self.firebase_auth_emulator_host)


@lru_cache
def get_settings() -> Settings:
    return Settings()
