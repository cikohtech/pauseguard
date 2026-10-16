"""GET /health: is the live stack up? (DEPLOYMENT §7.2)

Cloud Monitoring's uptime check calls it every 5 minutes from several regions, so each
dependency check is cheap, and the costly ones are cached per instance:

    firestore            one document read (a demo persona), on every call
    bigquery | sqlite    `SELECT 1` (TransactionRepo.ping, nothing billed), cached for 60 s
    gemini               count_tokens on GEMINI_MODEL (free, nothing generated), cached for 10 min

A failure is cached for 60 s only, so a recovery shows up quickly. Any failure answers 503 with
the same body, so the uptime check and its alert fire. Cloud Run reserves some paths ending in
"z" (it answers /healthz itself with a 404), so /health is the route; /healthz is a local alias.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import ServicesDep
from app.data.base import StateRepo, TransactionRepo
from app.log import get_logger
from app.models.schemas import HealthResponse

router = APIRouter(tags=["ops"])
log = get_logger(__name__)

PROBE_TIMEOUT_SECONDS = 8.0  # each check; the uptime check itself waits 20 s
TXN_TTL_SECONDS = 60.0
MODEL_TTL_SECONDS = 600.0
FAILURE_TTL_SECONDS = 60.0
PROBE_PERSONA = "cust_001"

ModelPing = Callable[[], Awaitable[object]]


@dataclass
class HealthProbe:
    state: StateRepo
    txn_repo: TransactionRepo
    model_ping: ModelPing
    clock: Callable[[], float] = time.monotonic
    _cache: dict[str, tuple[float, bool]] = field(default_factory=dict)

    async def check(self) -> dict[str, bool]:
        firestore, txn, model = await asyncio.gather(
            self._probe("firestore", self._firestore),
            self._cached(self.txn_repo.backend, TXN_TTL_SECONDS, self._txn),
            self._cached("gemini", MODEL_TTL_SECONDS, self.model_ping),
        )
        return {"firestore": firestore, self.txn_repo.backend: txn, "gemini": model}

    async def _firestore(self) -> None:
        await self.state.get_persona(PROBE_PERSONA)

    async def _txn(self) -> None:
        if not await asyncio.to_thread(self.txn_repo.ping):
            raise RuntimeError(f"{self.txn_repo.backend} ping failed")

    async def _cached(self, name: str, ttl: float, fn: Callable[[], Awaitable[object]]) -> bool:
        now = self.clock()
        if (hit := self._cache.get(name)) and hit[0] > now:
            return hit[1]
        ok = await self._probe(name, fn)
        self._cache[name] = (now + (ttl if ok else FAILURE_TTL_SECONDS), ok)
        return ok

    async def _probe(self, name: str, fn: Callable[[], Awaitable[object]]) -> bool:
        try:
            await asyncio.wait_for(fn(), PROBE_TIMEOUT_SECONDS)
        except Exception as e:  # any failure, timeouts included, means "not healthy"
            log.warning("health_dependency_failed", dependency=name, error=type(e).__name__)
            return False
        return True


@router.get(
    "/health",
    response_model=HealthResponse,
    responses={503: {"model": HealthResponse, "description": "A dependency is down"}},
    summary="Health, with dependency checks",
)
@router.get("/healthz", response_model=HealthResponse, include_in_schema=False)
async def health(services: ServicesDep) -> JSONResponse:
    """`ok` is true when Firestore, the transaction store (BigQuery in cloud) and Gemini all
    answer; otherwise 503 with the same body. BigQuery is cached for 60 s and Gemini for 10 min
    (a free `count_tokens` call), so uptime checks cost nothing."""
    assert services.health is not None
    deps = await services.health.check()
    body = HealthResponse(
        ok=all(deps.values()),
        model=services.settings.gemini_model,
        data_backend=services.settings.data_backend,
        dependencies=deps,
    )
    return JSONResponse(body.model_dump(), status_code=200 if body.ok else 503)
