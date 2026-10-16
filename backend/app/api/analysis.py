"""The check-in answer, from the API's side (POST /checks/{id}/messages).

The orchestrator runs as a background task. The request returns at its `done` event (the
customer's verdict and message), while the analyst-facing part (case file ∥ web search) carries on
in the same task; Cloud Run must therefore keep CPU allocated after the response
(`--no-cpu-throttling`, docs/DEPLOYMENT.md). Every event also goes to the SSE hub.

Never an error, never GREEN on failure (CLAUDE.md rule 4): if no `done` arrives within
AGENT_TIMEOUT_SECONDS + ANALYSIS_GRACE_SECONDS, or the pipeline crashes before it, the task is
cancelled and the customer gets AMBER + needs_review, with a case for an analyst.
"""

from __future__ import annotations

import asyncio
import time

from app.agents.casefile_agent import CaseFileRequest, fallback_case_file
from app.agents.explainer_agent import static_message
from app.agents.orchestrator import CheckStateError, new_id
from app.api.deps import Services
from app.data.analytics import analytics_row
from app.data.base import NotFoundError, utcnow
from app.log import get_logger
from app.models.schemas import (
    CaseRecord,
    CheckMessageRequest,
    CheckMessageResponse,
    CheckRecord,
    FusionResult,
    ProgressEvent,
    TxnRisk,
)
from app.telemetry import tracer

log = get_logger(__name__)

ANALYSIS_GRACE_SECONDS = 8.0  # on top of the orchestrator's own budget, before the safe answer
TIMEOUT_REASON = "The analysis did not finish in time; a specialist will review this payment"


def response_from_check(check: CheckRecord) -> CheckMessageResponse:
    """The `done` payload rebuilt from a stored check (SSE from another instance, retries)."""
    fusion, evidence = check.fusion, check.evidence
    return CheckMessageResponse(
        check_id=check.check_id,
        status=check.status,
        verdict=fusion.verdict if fusion else None,
        action=fusion.action if fusion else None,
        needs_review=fusion.needs_review if fusion else False,
        typology=evidence.typology_guess if evidence else None,
        confidence=evidence.typology_confidence if evidence else None,
        top_flags=fusion.top_flags if fusion else [],
        customer_message=check.customer_message,
        case_id=check.case_id,
        latency_ms=check.latency_ms,
    )


async def record_snapshot(services: Services, check_id: str) -> None:
    """Append the check's current state to checks_analytics. Never raises: analytics must not
    break a customer's request."""
    try:
        check = await services.state.get_check(check_id)
        if check is None:
            return
        case = await services.state.get_case(check.case_id) if check.case_id else None
        row = analytics_row(check, case=case, model=services.settings.gemini_model)
        await asyncio.to_thread(services.analytics.record, [row])
    except Exception:
        log.exception("analytics_write_failed", check_id=check_id)


def snapshot_later(services: Services, check_id: str) -> None:
    services.spawn(record_snapshot(services, check_id), name=f"analytics:{check_id}")


async def answer(
    services: Services, check: CheckRecord, msg: CheckMessageRequest
) -> CheckMessageResponse:
    check_id, t0 = check.check_id, time.perf_counter()
    loop = asyncio.get_running_loop()
    done: asyncio.Future[dict[str, object]] = loop.create_future()

    def on_event(event: ProgressEvent) -> None:
        services.hub.publish(check_id, event)
        if event.type == "done" and event.data is not None and not done.done():
            done.set_result(event.data)

    async def pipeline() -> None:
        # One trace per check in Cloud Trace: ADK's agent, model and tool spans nest under it.
        with tracer.start_as_current_span(
            "pauseguard.check", attributes={"check_id": check_id, "is_eval": check.is_eval}
        ) as span:
            try:
                outcome = await services.orchestrator.analyse(check_id, msg, on_event=on_event)
                span.set_attribute("verdict", outcome.fusion.verdict)
            except Exception as e:
                if not done.done():
                    done.set_exception(e)  # the request answers (409/404, or the safe AMBER)
                    return
                log.exception("analysis_failed_after_done", check_id=check_id)
        await record_snapshot(services, check_id)

    services.inflight.add(check_id)
    task = services.spawn(pipeline(), name=f"analyse:{check_id}")
    budget = services.settings.agent_timeout_seconds + ANALYSIS_GRACE_SECONDS
    try:
        data = await asyncio.wait_for(asyncio.shield(done), timeout=budget)
        return CheckMessageResponse.model_validate(data)
    except (CheckStateError, NotFoundError):
        raise
    except Exception as e:  # TimeoutError, or the pipeline crashed before `done`
        task.cancel()
        await asyncio.wait([task], timeout=1.0)
        log.error("analysis_fallback", check_id=check_id, error=type(e).__name__)
        return await safe_amber(services, check, int((time.perf_counter() - t0) * 1000))
    finally:
        services.inflight.discard(check_id)


async def safe_amber(services: Services, check: CheckRecord, total_ms: int) -> CheckMessageResponse:
    """AMBER + needs_review, a case with the deterministic case file, and the `done` event.
    The writes are best effort: if Firestore is what failed, the customer still gets an answer.
    """
    fusion = FusionResult(
        verdict="AMBER", action="COOL_OFF", reasons=[TIMEOUT_REASON], needs_review=True
    )
    message = static_message("AMBER", check.language, fusion)
    case_id = new_id("case")
    latency = check.latency_ms.model_copy(update={"total": total_ms})
    response = CheckMessageResponse(
        check_id=check.check_id,
        status="DONE",
        verdict="AMBER",
        action="COOL_OFF",
        needs_review=True,
        typology="UNKNOWN",
        confidence=0.0,
        customer_message=message,
        case_id=case_id,
        latency_ms=latency,
    )
    try:
        customer = await asyncio.to_thread(services.txn_repo.get_customer, check.customer_id)
        await services.state.update_check(
            check.check_id,
            status="DONE",
            fusion=fusion,
            customer_message=message,
            case_id=case_id,
            latency_ms=latency,
        )
        case_file = fallback_case_file(
            CaseFileRequest(
                transfer=check.transfer,
                txn=check.txn_risk or TxnRisk(score=0),
                fusion=fusion,
                check_id=check.check_id,
            )
        )
        await services.state.create_case(
            CaseRecord(
                case_id=case_id,
                check_id=check.check_id,
                customer_id=check.customer_id,
                customer_name=customer.full_name if customer else check.customer_id,
                customer_age=customer.age if customer else None,
                amount=check.transfer.amount,
                verdict="AMBER",
                typology="UNKNOWN",
                confidence=0.0,
                case_file=case_file,
                created_at=utcnow(),
            )
        )
    except Exception:
        log.exception("safe_amber_write_failed", check_id=check.check_id)
    services.hub.publish(
        check.check_id,
        ProgressEvent(type="done", stage="DONE", data=response.model_dump(mode="json")),
    )
    snapshot_later(services, check.check_id)
    return response
