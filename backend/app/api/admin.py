"""Ops routes (X-Admin-Token, from Secret Manager `admin-reset-token`).

    POST /admin/reset-demo   delete the 3 demo personas' checks and cases and the watchlist
                             entries analysts added, and put the seed entries back as seeded
                             (DEPLOYMENT §7.4: Cloud Scheduler calls this every 6 hours)
    POST /admin/purge-eval   delete the benchmark's checks (is_eval) and their cases, so a
                             benchmark run on the live stack leaves nothing in the console
    POST /admin/selftest     Aisyah's GREEN scenario end to end through Gemini; 503 when it
                             fails (DEPLOYMENT §7.3: Cloud Scheduler calls it daily, and a log
                             alert on `selftest_failed` emails the team)

Cloud Scheduler sends the same X-Admin-Token as the smoke test (infra/uptime.sh).
"""

from __future__ import annotations

import asyncio
import time

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.agents.scenarios import SCENARIOS
from app.api.analysis import answer
from app.api.deps import AdminDep, Services, ServicesDep
from app.api.errors import error_docs
from app.config import ASSETS_DIR
from app.data.seed import watchlist_entries
from app.log import get_logger
from app.models.schemas import (
    CheckMessageResponse,
    PurgeEvalResponse,
    ResetDemoResponse,
    SelftestResponse,
)
from app.tools.evidence_store import object_name

router = APIRouter(prefix="/admin", tags=["ops"])
log = get_logger(__name__)

DEMO_CUSTOMERS = sorted({s.customer_id for s in SCENARIOS.values()})
SELFTEST = SCENARIOS["aisyah"]
SELFTEST_PDF = ASSETS_DIR / "aisyah_tenancy.pdf"  # = data/demo/aisyah_tenancy.pdf


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
    entry, so the live demo can be re-run. Seed watchlist entries are put back as seeded (a
    REPORT_SCAM on Mrs Tan's case bumps their counts); the audit log and analytics history are
    kept."""
    state = services.state
    checks, cases, watchlist = await asyncio.gather(
        state.delete_checks_for(DEMO_CUSTOMERS),
        state.delete_cases_for(DEMO_CUSTOMERS),
        state.delete_watchlist(source="ANALYST_REPORT"),
    )
    seeds = watchlist_entries(ASSETS_DIR)
    await asyncio.gather(*(state.put_watchlist(e) for e in seeds))
    log.info("demo_reset", checks=checks, cases=cases, watchlist=watchlist, seeds=len(seeds))
    return ResetDemoResponse(
        checks_deleted=checks,
        cases_deleted=cases,
        watchlist_deleted=watchlist,
        seed_restored=len(seeds),
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


@router.post(
    "/selftest",
    response_model=SelftestResponse,
    responses=error_docs(403)
    | {503: {"model": SelftestResponse, "description": "The scenario did not come out GREEN"}},
    summary="Run Aisyah's GREEN scenario through Gemini",
)
async def selftest(services: ServicesDep, _: AdminDep) -> JSONResponse:
    """Starts Aisyah's S$3,200 rent deposit, attaches her tenancy agreement (PDF) and answers the
    check-in, exactly like the app does, through the real agents. Passes when the verdict is
    GREEN with no review. The check is marked as test traffic (kept out of /metrics) and the
    6-hourly reset removes it. 503 with the same body on failure."""
    result = await run_selftest(services)
    fields = result.model_dump(exclude={"expected", "scenario"})
    if result.passed:
        log.info("selftest_passed", **fields)
    else:
        log.error("selftest_failed", **fields)
    return JSONResponse(result.model_dump(mode="json"), status_code=200 if result.passed else 503)


async def run_selftest(services: Services) -> SelftestResponse:
    t0 = time.perf_counter()
    report = SelftestResponse(
        passed=False, scenario=SELFTEST.key, expected=list(SELFTEST.expected), latency_ms=0
    )
    try:
        started = await services.orchestrator.start(SELFTEST.create_request(), is_eval=True)
        report.check_id = started.check_id
        if started.status != "CHECKIN":
            report.verdict = started.verdict
            report.reason = f"no check-in (status {started.status}), so Gemini was not called"
            return report
        data = await asyncio.to_thread(SELFTEST_PDF.read_bytes)
        name = object_name(0, SELFTEST_PDF.name, "application/pdf")
        uri = await services.store.put(started.check_id, name, data, "application/pdf")
        await services.state.update_check(started.check_id, uploads=[uri])
        check = await services.state.get_check(started.check_id)
        assert check is not None
        done: CheckMessageResponse = await answer(
            services, check, SELFTEST.message(evidence_uris=(uri,))
        )
    except Exception as e:  # Firestore, BigQuery or the bucket: still a report, not a 500
        log.exception("selftest_error", check_id=report.check_id)
        report.reason = f"{type(e).__name__}: {str(e)[:200]}"
        return report
    finally:
        report.latency_ms = round((time.perf_counter() - t0) * 1000)
    report.verdict, report.needs_review = done.verdict, done.needs_review
    report.passed = done.verdict in SELFTEST.expected and not done.needs_review
    if not report.passed:
        review = " + needs_review" if done.needs_review else ""
        report.reason = f"expected {'/'.join(SELFTEST.expected)}, got {done.verdict}{review}"
    return report
