"""POST /admin/selftest (Aisyah through the agents, daily from Cloud Scheduler), the image's copies
of the seed watchlist and the tenancy PDF, and the per-check trace span."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.api import analysis as analysis_mod
from app.api.deps import Services
from app.config import ASSETS_DIR, REPO_ROOT
from app.data.memory_repo import MemoryStateRepo
from app.data.seed import seed_state
from app.data.sqlite_repo import SqliteTransactionRepo
from tests.api_support import (
    ADMIN,
    ANALYST,
    TAN,
    StubEvidence,
    build_services,
    client_for,
    make_settings,
)


@pytest.fixture
async def state(seed_dir: Path) -> MemoryStateRepo:
    repo = MemoryStateRepo()
    await seed_state(repo, seed_dir)
    return repo


@pytest.fixture
def evidence() -> StubEvidence:
    return StubEvidence()


@pytest.fixture
def services(
    tmp_path: Path, state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo, evidence: Any
) -> Services:
    # A 1 s budget keeps the timeout tests quick (the stub agents answer at once).
    settings = make_settings(tmp_path, agent_timeout_seconds=1.0)
    return build_services(tmp_path, state, sqlite_repo, evidence=evidence, settings=settings)


@pytest.fixture
async def client(services: Services) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(services) as c:
        yield c
    await services.drain()


@pytest.mark.parametrize(
    ("asset", "source"),
    [
        ("watchlist.json", "data/seed/watchlist.json"),
        ("aisyah_tenancy.pdf", "data/demo/aisyah_tenancy.pdf"),
    ],
)
def test_image_assets_match_their_sources(asset: str, source: str) -> None:
    # The Docker build context is backend/, so the API ships copies; they must not drift.
    assert (ASSETS_DIR / asset).read_bytes() == (REPO_ROOT / source).read_bytes(), (
        f"cp {source} backend/app/assets/{asset}"
    )


async def test_selftest_runs_aisyah_with_her_pdf_and_passes_green(
    client: httpx.AsyncClient, services: Services, evidence: StubEvidence
) -> None:
    assert (await client.post("/api/v1/admin/selftest", headers=ANALYST)).status_code == 403
    r = await client.post("/api/v1/admin/selftest", headers=ADMIN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["passed"] and body["verdict"] == "GREEN" and body["scenario"] == "aisyah"
    assert body["expected"] == ["GREEN"] and body["reason"] is None and body["attempts"] == 1
    check = await services.state.get_check(body["check_id"])
    assert check is not None and check.is_eval  # kept out of /metrics
    assert check.customer_id == "cust_003" and check.status == "DONE"
    [uri] = check.uploads
    assert uri.endswith("/0-aisyah_tenancy.pdf")
    stored = services.settings.local_uploads_dir / "checks" / check.check_id / Path(uri).name
    assert stored.read_bytes() == (ASSETS_DIR / "aisyah_tenancy.pdf").read_bytes()
    [req] = evidence.requests
    assert [i.uri for i in req.items] == [uri]


class WrongEvidence(StubEvidence):
    async def analyse(self, req: Any) -> Any:
        run = await super().analyse(req)
        run.analysis = TAN  # the model "sees" a scam in a tenancy agreement
        return run


@pytest.mark.parametrize("evidence", [WrongEvidence()])
async def test_a_wrong_verdict_fails_with_503_and_a_reason(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/admin/selftest", headers=ADMIN)
    assert r.status_code == 503
    body = r.json()
    assert not body["passed"] and body["verdict"] in ("AMBER", "RED")
    assert body["reason"].startswith("expected GREEN, got ")


@pytest.mark.parametrize("evidence", [StubEvidence(delay=30)])
async def test_two_timeouts_in_a_row_fail_as_amber_needs_review(
    client: httpx.AsyncClient, evidence: StubEvidence
) -> None:
    r = await client.post("/api/v1/admin/selftest", headers=ADMIN)
    assert r.status_code == 503
    body = r.json()
    assert body["verdict"] == "AMBER" and body["needs_review"] and body["attempts"] == 2
    miss = "expected GREEN, got AMBER + needs_review"
    assert body["reason"] == f"{miss} (attempt 1: {miss})"
    assert len(evidence.requests) == 2


class SlowOnce(StubEvidence):
    async def analyse(self, req: Any) -> Any:
        self.delay = 30 if not self.requests else 0  # one slow Gemini call, then a normal one
        return await super().analyse(req)


@pytest.mark.parametrize("evidence", [SlowOnce()])
async def test_one_slow_model_call_is_retried_and_passes(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/admin/selftest", headers=ADMIN)
    assert r.status_code == 200
    body = r.json()
    assert body["passed"] and body["attempts"] == 2 and body["reason"] is None


async def test_no_check_in_means_gemini_was_never_called(
    client: httpx.AsyncClient, services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(services.settings, "checkin_every_new_payee", False)
    monkeypatch.setattr(services.settings, "txn_green_fast_path_below", 101)
    r = await client.post("/api/v1/admin/selftest", headers=ADMIN)
    assert r.status_code == 503
    assert r.json()["verdict"] == "GREEN" and "Gemini was not called" in r.json()["reason"]


async def test_a_storage_failure_is_a_report_not_a_500(
    client: httpx.AsyncClient, services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def broken(*_: Any) -> str:
        raise OSError("bucket gone")

    monkeypatch.setattr(services.store, "put", broken)
    r = await client.post("/api/v1/admin/selftest", headers=ADMIN)
    assert r.status_code == 503 and r.json()["reason"] == "OSError: bucket gone"


async def test_reset_demo_restores_seed_counts(
    client: httpx.AsyncClient, services: Services
) -> None:
    seed = await services.state.get_watchlist("PHONE", "+65 8000 0147")
    assert seed is not None and seed.reported_count == 6
    await services.state.upsert_watchlist(
        "PHONE", "+65 8000 0147", source="ANALYST_REPORT", typologies=["GOV_OFFICIAL_IMPERSONATION"]
    )  # what REPORT_SCAM on Mrs Tan's case does
    bumped = await services.state.get_watchlist("PHONE", "+65 8000 0147")
    assert bumped is not None and bumped.reported_count == 7 and bumped.source == "SEED"
    r = await client.post("/api/v1/admin/reset-demo", headers=ADMIN)
    assert r.json()["seed_restored"] == 30
    back = await services.state.get_watchlist("PHONE", "+65 8000 0147")
    assert back == seed


async def test_each_check_answer_is_one_trace_span(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(analysis_mod, "tracer", provider.get_tracer("test"))
    body = (await client.post("/api/v1/admin/selftest", headers=ADMIN)).json()
    [span] = [s for s in exporter.get_finished_spans() if s.name == "pauseguard.check"]
    assert span.attributes is not None
    assert span.attributes["check_id"] == body["check_id"] and span.attributes["is_eval"] is True
    assert span.attributes["verdict"] == "GREEN"


def test_retry_with_backoff_on_quota_errors() -> None:
    from app.agents._runtime import shared_model

    retry = shared_model("gemini-retry-test").retry_options
    assert retry is not None and retry.http_status_codes == [429, 503]
    assert retry.attempts == 3 and (retry.initial_delay or 0) <= 1


def test_cloud_trace_is_set_up_once_on_cloud_run_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from google.adk.telemetry import google_cloud, setup

    from app import telemetry
    from app.config import Settings

    calls: list[Any] = []
    monkeypatch.setattr(telemetry, "_enabled", False)
    monkeypatch.delenv("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", raising=False)
    monkeypatch.setattr(google_cloud, "get_gcp_exporters", lambda **kw: calls.append(kw) or "h")
    monkeypatch.setattr(google_cloud, "get_gcp_resource", lambda project: f"res:{project}")
    monkeypatch.setattr(setup, "maybe_set_otel_providers", lambda h, otel_resource: None)

    local = Settings(_env_file=None)  # type: ignore[call-arg]
    assert not local.cloud_trace_enabled and not telemetry.setup_tracing(local)
    cloud = Settings(_env_file=None, K_SERVICE="pauseguard-api")  # type: ignore[call-arg]
    assert telemetry.setup_tracing(cloud) and telemetry.setup_tracing(cloud)
    assert calls == [{"enable_cloud_tracing": True}]  # once per process
    # Spans carry IDs and timings, never the customer's evidence.
    import os

    assert os.environ["ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS"] == "false"


def test_a_tracing_failure_never_stops_the_api(monkeypatch: pytest.MonkeyPatch) -> None:
    from google.adk.telemetry import google_cloud

    from app import telemetry
    from app.config import Settings

    def no_credentials(**_: Any) -> Any:
        raise RuntimeError("no credentials")

    monkeypatch.setattr(telemetry, "_enabled", False)
    monkeypatch.setattr(google_cloud, "get_gcp_exporters", no_credentials)
    s = Settings(_env_file=None, cloud_trace=True)  # type: ignore[call-arg]
    assert telemetry.setup_tracing(s) is False
