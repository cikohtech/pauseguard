"""Customer routes (API_SPEC "Customer endpoints"): a check, from transfer to the customer's choice.

POST /checks                      transaction risk -> GREEN at once, or the check-in question
POST /checks/{id}/messages        the check-in answer + evidence -> verdict and message
GET  /checks/{id}                 the check document (no case file)
GET  /checks/{id}/events          progress as Server-Sent Events
POST /checks/{id}/choice          what the customer did next
POST /checks/{id}/feedback        "was this helpful?"
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import APIRouter, Header, Request
from sse_starlette import EventSourceResponse

from app.api.analysis import answer, response_from_check, snapshot_later
from app.api.deps import CustomerDep, Services, ServicesDep
from app.api.errors import ApiError, conflict, error_docs, not_found
from app.api.events import TERMINAL
from app.data.base import utcnow
from app.models.schemas import (
    CheckMessageRequest,
    CheckMessageResponse,
    CheckRecord,
    ChoiceRequest,
    ChoiceResponse,
    CreateCheckRequest,
    CreateCheckResponse,
    FeedbackRecord,
    FeedbackRequest,
    FeedbackResponse,
    ProgressEvent,
)

router = APIRouter(prefix="/checks", tags=["customer"])

SSE_POLL_SECONDS = 0.7  # also the MVP UI's polling interval for GET /checks/{id}
SSE_MAX_SECONDS = 120.0


async def load_check(services: Services, check_id: str) -> CheckRecord:
    check = await services.state.get_check(check_id)
    if check is None:
        raise not_found(f"Check {check_id}")
    return check


@router.post(
    "",
    status_code=201,
    response_model=CreateCheckResponse,
    responses=error_docs(401, 422, 429),
    summary="Start a check for a transfer",
)
async def create_check(
    req: CreateCheckRequest,
    request: Request,
    services: ServicesDep,
    principal: CustomerDep,
    x_pauseguard_eval: Annotated[
        bool, Header(description="Benchmark traffic (admin token only): kept out of /metrics")
    ] = False,
) -> CreateCheckResponse:
    """Scores the transfer (no LLM, ~300 ms). A low score with no watchlist hit is **GREEN at
    once** (`status: DONE`); otherwise `status: CHECKIN` with the first check-in question.
    `customer_id` must be a customer of the (synthetic) bank. Rate-limited per IP and per
    customer."""
    if not principal.is_service:
        assert services.limiter is not None
        services.limiter.hit(request, req.customer_id)
    started = await services.orchestrator.start(
        req, is_eval=principal.is_service and x_pauseguard_eval
    )
    if started.status == "DONE":
        snapshot_later(services, started.check_id)
    return started


@router.post(
    "/{check_id}/messages",
    response_model=CheckMessageResponse,
    responses=error_docs(401, 404, 409, 422),
    summary="Answer the check-in (text, quick reply, evidence)",
)
async def post_message(
    check_id: str,
    msg: CheckMessageRequest,
    services: ServicesDep,
    _: CustomerDep,
) -> CheckMessageResponse:
    """Runs the agents and returns the verdict with the customer message, typically in 4–8 s.
    `evidence_uris` must come from `POST /uploads/sign` for this check; `pasted_text` is a pasted
    chat, analysed as evidence (max 3 evidence items in all). Progress is streamed on
    `GET /checks/{id}/events` meanwhile. **A timeout is not an error**: the answer is then AMBER
    with `needs_review: true`, and an analyst gets the case."""
    check = await load_check(services, check_id)
    if check.status != "CHECKIN" or check_id in services.inflight:
        raise conflict(f"Check {check_id} is {check.status}, not waiting for an answer")
    unknown = [u for u in msg.evidence_uris if u not in check.uploads]
    if unknown:
        raise ApiError(
            422,
            "VALIDATION_ERROR",
            "evidence_uris: use the gcs_uri returned by POST /uploads/sign for this check",
            details=[
                {"loc": ["body", "evidence_uris"], "msg": u, "type": "unknown_upload"}
                for u in unknown
            ],  # fmt: skip
        )
    return await answer(services, check, msg)


@router.get(
    "/{check_id}",
    response_model=CheckRecord,
    responses=error_docs(401, 404),
    summary="Get a check (customer-safe: no case file)",
)
async def get_check(
    check_id: str,
    services: ServicesDep,
    _: CustomerDep,
) -> CheckRecord:
    """The full check document: status, transfer, risk, messages, evidence analysis, verdict and
    message. The MVP UI may poll this every 700 ms instead of using the event stream."""
    return await load_check(services, check_id)


@router.get(
    "/{check_id}/events",
    responses={
        200: {"content": {"text/event-stream": {}}, "description": "Server-Sent Events"},
        **error_docs(401, 404),
    },
    summary="Progress events (Server-Sent Events)",
)
async def check_events(
    check_id: str,
    services: ServicesDep,
    _: CustomerDep,
) -> EventSourceResponse:
    """`event: status|partial|done|error`, `data:` a ProgressEvent JSON. Order: status
    ANALYSING_EVIDENCE, status CHECKING_INTEL, partial ANALYSING_EVIDENCE {flags, typology},
    partial CHECKING_INTEL {watchlist_matches}, status DECIDING, partial DECIDING {verdict,
    action, top_flags}, status WRITING, done {the POST /messages response}. Events already sent
    are replayed on connect; a finished check sends `done` at once. The stream ends after `done`
    or `error`. EventSource can't set headers: pass the ID token as `?access_token=`."""
    await load_check(services, check_id)
    return EventSourceResponse(_stream(services, check_id), ping=15)


def _sse(event: ProgressEvent) -> dict[str, str]:
    return {"event": event.type, "data": event.model_dump_json()}


def _done_from(check: CheckRecord) -> ProgressEvent:
    data = response_from_check(check).model_dump(mode="json")
    return ProgressEvent(type="done", stage="DONE", data=data)


async def _stream(services: Services, check_id: str) -> AsyncIterator[dict[str, str]]:
    check = await services.state.get_check(check_id)
    if check is not None and check.status == "DONE":
        yield _sse(_done_from(check))
        return
    deadline = time.monotonic() + SSE_MAX_SECONDS
    with services.hub.subscribe(check_id) as (history, queue):
        for event in history:
            yield _sse(event)
            if event.type in TERMINAL:
                return
        while True:
            try:
                event = await asyncio.wait_for(queue.get(), SSE_POLL_SECONDS)
            except TimeoutError:
                # The analysis may run on another instance: the check document has the result.
                check = await services.state.get_check(check_id)
                if check is not None and check.status == "DONE":
                    yield _sse(_done_from(check))
                    return
                if time.monotonic() > deadline:
                    yield _sse(ProgressEvent(type="error", data={"message": "No result yet"}))
                    return
                continue
            yield _sse(event)
            if event.type in TERMINAL:
                return


@router.post(
    "/{check_id}/choice",
    response_model=ChoiceResponse,
    responses=error_docs(401, 404, 409, 422),
    summary="Record what the customer chose",
)
async def post_choice(
    check_id: str,
    req: ChoiceRequest,
    services: ServicesDep,
    _: CustomerDep,
) -> ChoiceResponse:
    """`COOL_OFF` (pause 24 h), `CALLED_CONTACT`, `CANCELLED` or `PROCEEDED`. PROCEEDED is
    allowed for GREEN, and for AMBER only with `confirmed: true` (the "I understand the risk"
    dialog); a RED payment is held for an analyst, so PROCEEDED is a 409."""
    check = await load_check(services, check_id)
    if check.status != "DONE" or check.fusion is None:
        raise conflict(f"Check {check_id} has no verdict yet")
    verdict = check.fusion.verdict
    if req.choice == "PROCEEDED" and verdict == "RED":
        raise conflict("This payment is on hold for review; it can't be sent from here")
    if req.choice == "PROCEEDED" and verdict == "AMBER" and not req.confirmed:
        raise conflict("Confirm that you understand the risk first (confirmed: true)")
    await services.state.update_check(check_id, customer_choice=req.choice)
    snapshot_later(services, check_id)
    return ChoiceResponse(check_id=check_id, customer_choice=req.choice)


@router.post(
    "/{check_id}/feedback",
    status_code=201,
    response_model=FeedbackResponse,
    responses=error_docs(401, 404, 422),
    summary="Was this check helpful?",
)
async def post_feedback(
    check_id: str,
    req: FeedbackRequest,
    services: ServicesDep,
    _: CustomerDep,
) -> FeedbackResponse:
    await load_check(services, check_id)
    feedback_id = await services.state.add_feedback(
        FeedbackRecord(check_id=check_id, helpful=req.helpful, comment=req.comment, ts=utcnow())
    )
    return FeedbackResponse(feedback_id=feedback_id)
