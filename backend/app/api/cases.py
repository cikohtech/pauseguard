"""Analyst routes (API_SPEC "Analyst endpoints"; custom claim role=analyst).

    GET  /cases                 case summaries (the console mainly uses the Firestore listener)
    GET  /cases/{id}            the full case: case file, evidence read URLs, flags, risk, intel
    POST /cases/{id}/decision   RELEASE | HOLD | ESCALATE | REPORT_SCAM (+ watchlist upsert)

Every decision appends an `audit` entry. Only analyst actions change the watchlist; no agent has
a tool that writes to it (SECURITY_PRIVACY §1).
"""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query, Request

from app.api.analysis import snapshot_later
from app.api.deps import AnalystDep, Services, ServicesDep
from app.api.errors import error_docs, not_found
from app.data.base import utcnow
from app.data.normalise import normalise_domain, normalise_url, normalise_watchlist_value
from app.log import get_logger
from app.models.schemas import (
    AnalystAction,
    AuditEntry,
    CaseDetail,
    CaseRecord,
    CaseStatus,
    CaseSummary,
    CheckRecord,
    DecisionRequest,
    DecisionResponse,
    EvidenceLink,
    Typology,
    WatchlistType,
)
from app.tools.evidence_store import content_type_of
from app.tools.watchlist import entities_from_text, merge_entities

router = APIRouter(prefix="/cases", tags=["analyst"])
log = get_logger(__name__)

STATUS_FOR_ACTION: dict[AnalystAction, CaseStatus] = {
    "RELEASE": "RELEASED",
    "HOLD": "HELD",
    "ESCALATE": "ESCALATED",
    "REPORT_SCAM": "REPORTED",
}
# Hosts that many unrelated people share: a scammer's link there is reported as the full URL,
# never as the domain (blocking t.me would hold every future Telegram link). A bare link to one
# is not reported at all.
SHARED_HOSTS = frozenset(
    {
        "t.me", "telegram.me", "wa.me", "api.whatsapp.com", "chat.whatsapp.com", "line.me",
        "bit.ly", "tinyurl.com", "t.co", "goo.gl", "forms.gle", "linktr.ee",
        "docs.google.com", "drive.google.com", "sites.google.com", "facebook.com",
        "instagram.com", "tiktok.com", "youtube.com", "youtu.be",
    }
)  # fmt: skip
# Real authorities' domains that scammers quote for credibility are never reported.
NEVER_REPORTED_SUFFIXES = (".gov.sg", ".gov", ".edu.sg", ".mil")


@router.get(
    "",
    response_model=list[CaseSummary],
    responses=error_docs(401, 403),
    summary="List cases",
)
async def list_cases(
    services: ServicesDep,
    _: AnalystDep,
    status: Annotated[CaseStatus | None, Query(description="e.g. OPEN")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[CaseSummary]:
    """Newest first. The console's queue reads Firestore in real time; this is for tests and
    fallback."""
    cases = await services.state.list_cases(status=status, limit=limit)
    return [_summary(c) for c in cases]


def _summary(c: CaseRecord) -> CaseSummary:
    return CaseSummary(
        case_id=c.case_id,
        check_id=c.check_id,
        customer_name=c.customer_name,
        customer_age=c.customer_age,
        amount=c.amount,
        verdict=c.verdict,
        typology=c.typology,
        confidence=c.confidence,
        status=c.status,
        title=c.case_file.title if c.case_file else None,
        created_at=c.created_at,
    )


async def _load(services: Services, case_id: str) -> tuple[CaseRecord, CheckRecord]:
    case = await services.state.get_case(case_id)
    if case is None:
        raise not_found(f"Case {case_id}")
    check = await services.state.get_check(case.check_id)
    if check is None:
        raise not_found(f"Check {case.check_id} of case {case_id}")
    return case, check


@router.get(
    "/{case_id}",
    response_model=CaseDetail,
    responses=error_docs(401, 403, 404),
    summary="Get a case with its evidence, risk, intel and audit history",
)
async def get_case(
    case_id: str,
    request: Request,
    services: ServicesDep,
    _: AnalystDep,
) -> CaseDetail:
    """`case.case_file` is null for a few seconds after the case appears (the case-file agent
    runs after the customer has their answer). `evidence_links` are signed read URLs valid for 5
    minutes; their `index` matches `evidence_index` on the flags."""
    case, check = await _load(services, case_id)
    audit = await services.state.list_audit(case_id)
    return CaseDetail(
        case=case,
        transfer=check.transfer,
        txn_risk=check.txn_risk,
        messages=check.messages,
        evidence=check.evidence,
        evidence_links=await _evidence_links(services, check, str(request.base_url)),
        intel=check.intel,
        fusion=check.fusion,
        customer_choice=check.customer_choice,
        audit=audit,
    )


async def _evidence_links(
    services: Services, check: CheckRecord, base_url: str
) -> list[EvidenceLink]:
    answers = [m for m in check.messages if m.role == "customer"]
    uris = answers[-1].evidence_uris if answers else []
    links = []
    for i, uri in enumerate(uris):
        try:
            url = await services.store.read_url(uri, base_url=base_url)
        except Exception:
            log.exception("evidence_link_failed", check_id=check.check_id, index=i)
            continue
        links.append(EvidenceLink(index=i, url=url, content_type=content_type_of(uri)))
    return links


@router.post(
    "/{case_id}/decision",
    response_model=DecisionResponse,
    responses=error_docs(401, 403, 404, 422),
    summary="Decide a case",
)
async def decide(
    case_id: str,
    req: DecisionRequest,
    services: ServicesDep,
    principal: AnalystDep,
) -> DecisionResponse:
    """Sets the case status (RELEASED, HELD, ESCALATED, REPORTED) and appends an audit entry.
    **REPORT_SCAM** also upserts every phone, account and domain the case extracted into the
    watchlist (source ANALYST_REPORT; an existing entry's reported_count goes up). Links on shared
    platforms (t.me, bit.ly…) are reported as the full URL, and government domains never.
    `watchlist_added` is the number of entries reported."""
    case, check = await _load(services, case_id)
    now = utcnow()
    reported: list[tuple[WatchlistType, str]] = []
    if req.action == "REPORT_SCAM":
        reported = await _report(services, case, check)
    status = STATUS_FOR_ACTION[req.action]
    await services.state.update_case(
        case_id,
        status=status,
        decided_at=now,
        decision_note=req.note,
        assigned_to=principal.actor,
    )
    await services.state.append_audit(
        AuditEntry(actor=principal.actor, action=req.action, case_id=case_id, ts=now, note=req.note)
    )
    if reported:
        await services.state.append_audit(
            AuditEntry(
                actor=principal.actor,
                action="WATCHLIST_ADD",
                case_id=case_id,
                ts=now,
                note=", ".join(f"{t} {v}" for t, v in reported),
            )
        )
    snapshot_later(services, check.check_id)
    log.info(
        "case_decided", case_id=case_id, action=req.action, actor=principal.actor,
        watchlist_added=len(reported),
    )  # fmt: skip
    return DecisionResponse(case_id=case_id, status=status, watchlist_added=len(reported))


def reportable_entities(check: CheckRecord) -> list[tuple[WatchlistType, str]]:
    """(type, normalised value) for every entity the case extracted: the evidence agent's
    entities, the pasted chat's phones/URLs/accounts and the payee account. The customer's own
    answer and their trusted contact are not scam entities."""
    pasted = [m.pasted_text for m in check.messages if m.role == "customer" and m.pasted_text]
    evidence = check.evidence.entities if check.evidence else None
    found = merge_entities(entities_from_text(*pasted), evidence)
    pairs: list[tuple[WatchlistType, str]] = [("PHONE", p) for p in found.phones]
    pairs += [("ACCOUNT", a) for a in [*found.accounts, check.transfer.account_number]]
    for url in found.urls:
        host = normalise_domain(url)
        if not host or host.endswith(NEVER_REPORTED_SUFFIXES):
            continue
        if host in SHARED_HOSTS:
            if normalise_url(url) != host:  # a path on a shared platform: that link only
                pairs.append(("URL", url))
        else:
            pairs.append(("DOMAIN", host))
    out: list[tuple[WatchlistType, str]] = []
    for type_, raw in pairs:
        value = normalise_watchlist_value(type_, raw)
        if value.strip("+") and (type_, value) not in out:
            out.append((type_, value))
    return out


async def _report(
    services: Services, case: CaseRecord, check: CheckRecord
) -> list[tuple[WatchlistType, str]]:
    entities = reportable_entities(check)
    customer = await asyncio.to_thread(services.txn_repo.get_customer, check.customer_id)
    if customer and customer.trusted_contact_phone:
        own = ("PHONE", normalise_watchlist_value("PHONE", customer.trusted_contact_phone))
        entities = [e for e in entities if e != own]
    typologies: list[Typology] = [] if case.typology in ("NONE", "UNKNOWN") else [case.typology]
    await asyncio.gather(
        *(
            services.state.upsert_watchlist(t, v, source="ANALYST_REPORT", typologies=typologies)
            for t, v in entities
        )
    )
    return entities
