"""GET /health: dependency checks (Firestore, transaction store, Gemini), their caches, and 503
when one fails, so the Cloud Monitoring uptime check alerts (DEPLOYMENT §7.2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.api.health import FAILURE_TTL_SECONDS, MODEL_TTL_SECONDS, TXN_TTL_SECONDS, HealthProbe
from app.config import Settings
from app.data.memory_repo import MemoryStateRepo
from app.data.sqlite_repo import SqliteTransactionRepo
from tests.api_support import build_services, client_for


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Model:
    def __init__(self) -> None:
        self.calls, self.fail = 0, False

    async def __call__(self) -> None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("vertex down")


@pytest.fixture
def model() -> Model:
    return Model()


@pytest.fixture
def probe(sqlite_repo: SqliteTransactionRepo, model: Model) -> HealthProbe:
    return HealthProbe(MemoryStateRepo(), sqlite_repo, model, clock=Clock())


@pytest.mark.parametrize("path", ["/health", "/healthz"])
async def test_health_reports_every_dependency(
    path: str, tmp_path: Path, sqlite_repo: SqliteTransactionRepo
) -> None:
    # /health is the one Cloud Run serves (it reserves /healthz); /healthz is a local alias.
    services = build_services(tmp_path, MemoryStateRepo(), sqlite_repo)
    async with client_for(services) as client:
        r = await client.get(path)
    assert r.status_code == 200
    assert r.json() == {
        "ok": True,
        "model": "gemini-test",
        "data_backend": "sqlite",
        "dependencies": {"firestore": True, "sqlite": True, "gemini": True},
    }


async def test_a_failing_dependency_answers_503_with_the_same_body(
    tmp_path: Path, sqlite_repo: SqliteTransactionRepo, model: Model
) -> None:
    model.fail = True
    services = build_services(tmp_path, MemoryStateRepo(), sqlite_repo, model_ping=model)
    async with client_for(services) as client:
        r = await client.get("/health")
    assert r.status_code == 503
    assert r.json()["ok"] is False
    assert r.json()["dependencies"] == {"firestore": True, "sqlite": True, "gemini": False}


async def test_model_check_is_cached_and_a_failure_only_briefly(
    probe: HealthProbe, model: Model
) -> None:
    clock = probe.clock
    assert isinstance(clock, Clock)
    assert (await probe.check())["gemini"] and model.calls == 1
    clock.now += MODEL_TTL_SECONDS - 1
    await probe.check()
    assert model.calls == 1  # 10 minutes of uptime checks, one count_tokens call
    clock.now += 2
    model.fail = True
    assert not (await probe.check())["gemini"] and model.calls == 2
    clock.now += FAILURE_TTL_SECONDS + 1
    model.fail = False
    assert (await probe.check())["gemini"] and model.calls == 3  # recovery seen within a minute


async def test_transaction_store_ping_is_cached_for_a_minute(
    probe: HealthProbe, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []

    def ping() -> bool:
        calls.append(1)
        return len(calls) > 1  # down first, then back

    monkeypatch.setattr(probe.txn_repo, "ping", ping)
    assert (await probe.check())["sqlite"] is False
    clock = probe.clock
    assert isinstance(clock, Clock)
    clock.now += FAILURE_TTL_SECONDS - 1
    assert (await probe.check())["sqlite"] is False and len(calls) == 1
    clock.now += 2
    assert (await probe.check())["sqlite"] is True and len(calls) == 2
    clock.now += TXN_TTL_SECONDS - 1
    await probe.check()
    assert len(calls) == 2


async def test_firestore_is_read_on_every_call_and_a_hang_times_out(
    probe: HealthProbe, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio

    from app.api import health as health_mod

    async def hang(_customer_id: str) -> None:
        await asyncio.sleep(10)

    monkeypatch.setattr(health_mod, "PROBE_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(probe.state, "get_persona", hang)
    assert (await probe.check())["firestore"] is False


def test_cors_allows_configured_origin(tmp_path: Path, sqlite_repo: SqliteTransactionRepo) -> None:
    from fastapi.testclient import TestClient

    from app.main import create_app
    from tests.api_support import make_settings

    settings = make_settings(tmp_path, allowed_origins="http://localhost:5173,https://x.web.app")
    services = build_services(tmp_path, MemoryStateRepo(), sqlite_repo, settings=settings)
    client = TestClient(create_app(settings, services=services))

    resp = client.get("/health", headers={"Origin": "https://x.web.app"})

    assert resp.headers["access-control-allow-origin"] == "https://x.web.app"


def test_auth_disabled_is_rejected_on_cloud_run() -> None:
    with pytest.raises(ValueError, match="AUTH_DISABLED"):
        Settings(auth_disabled=True, K_SERVICE="pauseguard-api", _env_file=None)  # type: ignore[call-arg]


def test_bigquery_ping_reads_no_table() -> None:
    # Once a minute from the uptime checks: a query that reads a table bills at least 10 MB.
    from app.data.bigquery_repo import BigQueryTransactionRepo

    sql: list[str] = []
    repo = BigQueryTransactionRepo.__new__(BigQueryTransactionRepo)
    repo._rows = lambda q, **_: sql.append(q) or []  # type: ignore[method-assign,func-returns-value]
    assert repo.ping() and sql == ["SELECT 1"]
