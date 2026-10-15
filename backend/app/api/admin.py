"""Ops routes (X-Admin-Token, from Secret Manager `admin-reset-token`).

    POST /admin/reset-demo   delete the 3 demo personas' checks and cases, and the watchlist
                             entries analysts added; the seed entries stay (DEPLOYMENT §7: Cloud
                             Scheduler calls this every 6 hours so the live demo stays clean)
    POST /admin/purge-eval   delete the benchmark's checks (is_eval) and their cases, so a
                             benchmark run on the live stack leaves nothing in the console

The daily `/admin/selftest` (Aisyah through Gemini) arrives with phase 10 Pass B.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter

from app.agents.scenarios import SCENARIOS
from app.api.deps import AdminDep, ServicesDep
from app.api.errors import error_docs
from app.log import get_logger
from app.models.schemas import PurgeEvalResponse, ResetDemoResponse

router = APIRouter(prefix="/admin", tags=["ops"])
log = get_logger(__name__)

DEMO_CUSTOMERS = sorted({s.customer_id for s in SCENARIOS.values()})


@router.post(
    "/reset-demo",
    response_model=ResetDemoResponse,
    responses=error_docs(403),
    summary="Reset the demo personas",
)
async def reset_demo(
    services: ServicesDep,
    _: AdminDep,
) -> ResetDemoResponse:
    """Removes the checks and cases of cust_001–cust_003 and every ANALYST_REPORT watchlist
    entry, so the live demo can be re-run. Seed watchlist entries, the audit log and analytics
    history are kept."""
    state = services.state
    checks, cases, watchlist = await asyncio.gather(
        state.delete_checks_for(DEMO_CUSTOMERS),
        state.delete_cases_for(DEMO_CUSTOMERS),
        state.delete_watchlist(source="ANALYST_REPORT"),
    )
    log.info("demo_reset", checks=checks, cases=cases, watchlist=watchlist)
    return ResetDemoResponse(
        checks_deleted=checks, cases_deleted=cases, watchlist_deleted=watchlist
    )


@router.post(
    "/purge-eval",
    response_model=PurgeEvalResponse,
    responses=error_docs(403),
    summary="Delete benchmark checks and cases",
)
async def purge_eval(
    services: ServicesDep,
    _: AdminDep,
) -> PurgeEvalResponse:
    """Removes every check marked as benchmark traffic (`X-PauseGuard-Eval`) and the cases they
    opened, so a benchmark run (`eval/run_benchmark.py --api`) leaves nothing in the analyst
    queue. Their `checks_analytics` rows stay (marked `is_eval`, left out of /metrics)."""
    checks, cases = await services.state.delete_eval_checks()
    log.info("eval_purged", checks=checks, cases=cases)
    return PurgeEvalResponse(checks_deleted=checks, cases_deleted=cases)
