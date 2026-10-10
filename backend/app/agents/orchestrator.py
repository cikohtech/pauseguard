"""Orchestrator (AGENTS_SPEC §7): one check, from transfer to verdict to case file.

    orch = Orchestrator(txn_repo=..., state=...)
    started = await orch.start(CreateCheckRequest(...))          # POST /checks
    outcome = await orch.analyse(check_id, CheckMessageRequest(...), on_event=cb)   # .../messages
    outcome = await orch.run_check(create_req, message_req)     # both (CLI, benchmark)

start():   transaction risk ∥ payee-account watchlist lookup ∥ customer lookup (no LLM).
           Score < 30 and no watchlist hit -> GREEN at once; otherwise a templated check-in.
analyse(): customer-facing part, inside AGENT_TIMEOUT_SECONDS:
             evidence agent ∥ watchlist lookup of the payee account and of the entities a regex
             finds in the customer's text -> watchlist lookup of the entities the evidence agent
             found -> fusion (deterministic) -> explainer (or the GREEN template) -> `done`
           analyst-facing part (AMBER/RED only), inside CASEFILE_TIMEOUT_SECONDS:
             case-file agent ∥ Scam-Intel agent (web search on unknown sites and platforms)
The verdict never waits for web search: fusion does not read web findings, so search runs after
the customer has their answer (and never for GREEN). Timeouts and failures give AMBER +
needs_review, and a verdict that is already RED is never downgraded by a slow explainer.
Every step reports progress through `on_event` (SSE or Firestore polling in the API), results
are persisted to the StateRepo (checks/{id}, cases/{id}), and one JSON log line per check
carries the per-agent latency and tokens.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import secrets
import statistics
import sys
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime

from app.agents.casefile_agent import CaseFileAgent, CaseFileRequest, fallback_case_file
from app.agents.evidence_agent import EvidenceAgent, EvidenceItem, EvidenceRequest, EvidenceRun
from app.agents.explainer_agent import (
    ExplainerAgent,
    ExplainRequest,
    green_message,
    lang_of,
    static_message,
)
from app.agents.intel_agent import IntelAgent, IntelRequest
from app.config import Settings, get_settings
from app.data.base import NotFoundError, StateRepo, TransactionRepo, as_utc, utcnow
from app.log import get_logger
from app.models.schemas import (
    CaseFile,
    CaseRecord,
    ChatMessage,
    CheckInQuestion,
    CheckMessageRequest,
    CheckMessageResponse,
    CheckRecord,
    CreateCheckRequest,
    CreateCheckResponse,
    Customer,
    CustomerMessage,
    Entities,
    EvidenceAnalysis,
    FusionResult,
    IntelResult,
    Language,
    LatencyMs,
    ProgressEvent,
    ProgressEventType,
    ProgressStage,
    TokenUsage,
    TxnRisk,
    WatchlistMatch,
)
from app.policy.fusion import Thresholds, fuse
from app.tools.txn_features import risk_from_snapshot
from app.tools.watchlist import entities_from_text, lookup_entities, merge_entities

log = get_logger(__name__)

EventCallback = Callable[[ProgressEvent], Awaitable[None] | None]
MIN_EXPLAINER_SECONDS = 1.0  # less budget than this left: use the static message for the verdict

QUICK_REPLIES = {
    "en": [
        "A government officer",
        "A job recruiter",
        "An investment group",
        "A friend or family member",
        "A seller",
        "No one, it's my own payment",
    ],
    "zh": ["政府官员", "工作招聘人员", "投资群组", "朋友或家人", "卖家", "没有人，是我自己要付的"],
}
QUESTION = {
    "en": "Who asked you to make this payment? Did someone contact you first?",
    "zh": "这笔转账是谁让您付的？有人先联系您吗？",
}
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class CheckStateError(RuntimeError):
    """The check is not waiting for a check-in answer (the API maps this to 409)."""


def new_id(prefix: str) -> str:
    """A time-ordered, ULID-style ID: 'chk_01J9...' (48-bit ms timestamp + 80 random bits)."""
    n = (time.time_ns() // 1_000_000) << 80 | secrets.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[n & 31])
        n >>= 5
    return f"{prefix}_{''.join(reversed(chars))}"


def checkin_question(language: Language) -> CheckInQuestion:
    lang = lang_of(language)
    return CheckInQuestion(text=QUESTION[lang], quick_replies=QUICK_REPLIES[lang])


def _ms(since: float) -> int:
    return round((time.perf_counter() - since) * 1000)


def _total(tokens: dict[str, TokenUsage]) -> TokenUsage:
    return TokenUsage(
        in_=sum(t.in_ for t in tokens.values()), out=sum(t.out for t in tokens.values())
    )


@dataclass
class AnalysisOutcome:
    response: CheckMessageResponse
    fusion: FusionResult
    intel: IntelResult
    evidence: EvidenceRun | None
    case_file: CaseFile | None
    latency: LatencyMs
    tokens: dict[str, TokenUsage] = field(default_factory=dict)
    pipeline_ms: int = 0  # including the analyst-facing part


@dataclass
class CheckOutcome:
    started: CreateCheckResponse
    analysis: AnalysisOutcome | None = None

    @property
    def verdict(self) -> str | None:
        return self.analysis.response.verdict if self.analysis else self.started.verdict

    @property
    def customer_message(self) -> CustomerMessage | None:
        if self.analysis:
            return self.analysis.response.customer_message
        return self.started.customer_message


class Orchestrator:
    def __init__(
        self,
        *,
        txn_repo: TransactionRepo,
        state: StateRepo,
        settings: Settings | None = None,
        evidence: EvidenceAgent | None = None,
        intel: IntelAgent | None = None,
        explainer: ExplainerAgent | None = None,
        casefile: CaseFileAgent | None = None,
        thresholds: Thresholds | None = None,
    ):
        self.settings = settings or get_settings()
        self.txn_repo = txn_repo
        self.state = state
        self.evidence = evidence or EvidenceAgent(settings=self.settings)
        self.intel = intel or IntelAgent(settings=self.settings)
        self.explainer = explainer or ExplainerAgent(settings=self.settings)
        self.casefile = casefile or CaseFileAgent(settings=self.settings)
        self.thresholds = thresholds or Thresholds.from_settings(self.settings)

    # --- POST /checks ------------------------------------------------------------------------

    async def start(
        self, req: CreateCheckRequest, *, as_of: datetime | None = None, check_id: str | None = None
    ) -> CreateCheckResponse:
        t0 = time.perf_counter()
        check_id = check_id or new_id("chk")
        now = as_utc(as_of)
        transfer = req.transfer
        snapshot, payee_matches, customer = await asyncio.gather(
            asyncio.to_thread(
                self.txn_repo.risk_snapshot, req.customer_id, transfer.account_number, as_of=now
            ),
            lookup_entities(self.state, accounts=[transfer.account_number]),
            asyncio.to_thread(self.txn_repo.get_customer, req.customer_id),
        )
        txn = risk_from_snapshot(snapshot, transfer, now=now, watchlist_hit=bool(payee_matches))
        language = lang_of(req.language or (customer.preferred_language if customer else "en"))
        txn_ms = _ms(t0)
        record = CheckRecord(
            check_id=check_id,
            customer_id=req.customer_id,
            created_at=utcnow(),
            status="CHECKIN",
            transfer=transfer,
            language=language,
            txn_risk=txn,
            latency_ms=LatencyMs(txn=txn_ms),
        )

        if txn.score < self.settings.txn_green_fast_path_below and not payee_matches:
            message = green_message(language)
            record.status = "DONE"
            record.fusion = FusionResult(
                verdict="GREEN",
                action="PROCEED",
                reasons=[f"Low transaction risk ({txn.score}); no check-in needed"],
            )
            record.customer_message = message
            record.latency_ms.total = txn_ms
            await self.state.create_check(record)
            log.info(
                "check_done",
                check_id=check_id,
                verdict="GREEN",
                fast_path=True,
                txn_score=txn.score,
                latency_ms={"txn": txn_ms, "total": txn_ms},
                tokens={"in": 0, "out": 0},
            )
            return CreateCheckResponse(
                check_id=check_id,
                status="DONE",
                txn_risk=txn,
                verdict="GREEN",
                customer_message=message,
            )

        question = checkin_question(language)
        record.messages = [ChatMessage(role="assistant", text=question.text, ts=record.created_at)]
        await self.state.create_check(record)
        log.info("check_started", check_id=check_id, txn_score=txn.score, txn_ms=txn_ms)
        return CreateCheckResponse(
            check_id=check_id, status="CHECKIN", txn_risk=txn, question=question
        )

    # --- POST /checks/{id}/messages ----------------------------------------------------------

    async def analyse(
        self, check_id: str, msg: CheckMessageRequest, *, on_event: EventCallback | None = None
    ) -> AnalysisOutcome:
        t0 = time.perf_counter()
        deadline = t0 + self.settings.agent_timeout_seconds
        check = await self.state.get_check(check_id)
        if check is None:
            raise NotFoundError(f"checks/{check_id}")
        if check.status != "CHECKIN":
            raise CheckStateError(f"check {check_id} is {check.status}, not waiting for an answer")
        transfer = check.transfer
        txn = check.txn_risk or TxnRisk(score=0)

        await self.state.append_check_message(
            check_id,
            ChatMessage(
                role="customer",
                text=msg.text or msg.quick_reply or "",
                evidence_uris=msg.evidence_uris,
                pasted_text=msg.pasted_text,
                ts=utcnow(),
            ),
        )
        await self.state.update_check(check_id, status="ANALYSING")
        await _emit(on_event, "status", "ANALYSING_EVIDENCE")
        await _emit(on_event, "status", "CHECKING_INTEL")

        customer_task = asyncio.create_task(
            asyncio.to_thread(self.txn_repo.get_customer, check.customer_id)
        )
        items = [EvidenceItem(uri=u) for u in msg.evidence_uris]
        if msg.pasted_text:
            items.append(EvidenceItem(text=msg.pasted_text))
        ev_req = EvidenceRequest(
            customer_text=msg.text,
            quick_reply=msg.quick_reply,
            items=items,
            transfer=transfer,
            check_id=check_id,
        )
        quick = entities_from_text(msg.text, msg.pasted_text)
        tokens: dict[str, TokenUsage] = {}
        failures: list[str] = []

        # Evidence agent ∥ watchlist (payee account + entities in the customer's own text).
        ev_task = asyncio.create_task(self.evidence.analyse(ev_req))
        t_wl = time.perf_counter()
        matches, wl_ok = await self._lookup(
            phones=quick.phones,
            urls=quick.urls,
            accounts=[transfer.account_number, *quick.accounts],
        )
        watchlist_ms = _ms(t_wl)
        evidence_run: EvidenceRun | None = None
        try:
            evidence_run = await asyncio.wait_for(ev_task, max(deadline - time.perf_counter(), 0))
        except TimeoutError:
            failures.append("evidence: timeout")
        except Exception as e:  # a bug, not a model error (those are handled inside the agent)
            log.exception("evidence_crashed", check_id=check_id)
            failures.append(f"evidence: {type(e).__name__}")
        evidence = evidence_run.analysis if evidence_run else None
        if evidence_run:
            tokens["evidence"] = evidence_run.tokens
            if evidence_run.failed:
                failures.append(f"evidence: {evidence_run.error}")
            await _emit(
                on_event,
                "partial",
                "ANALYSING_EVIDENCE",
                {
                    "flags": [f.code for f in evidence.red_flags] if evidence else [],
                    "typology": evidence.typology_guess if evidence else None,
                },
            )

        # Second watchlist pass: the phones, URLs and accounts the evidence agent found.
        if evidence:
            t_wl = time.perf_counter()
            found, ok = await self._lookup(
                phones=evidence.entities.phones,
                urls=evidence.entities.urls,
                accounts=evidence.entities.accounts,
            )
            matches, wl_ok, watchlist_ms = matches + found, wl_ok and ok, watchlist_ms + _ms(t_wl)
        if not wl_ok:
            failures.append("watchlist: lookup failed")
        intel = IntelResult(watchlist_matches=_dedupe(matches))
        await _emit(
            on_event,
            "partial",
            "CHECKING_INTEL",
            {"watchlist_matches": len(intel.watchlist_matches)},
        )

        await _emit(on_event, "status", "DECIDING")
        fusion = fuse(
            txn,
            evidence,
            intel,
            amount=transfer.amount,
            analysis_failed=bool(failures),
            thresholds=self.thresholds,
        )
        verdict_ms = _ms(t0)
        await _emit(
            on_event,
            "partial",
            "DECIDING",
            {
                "verdict": fusion.verdict,
                "action": fusion.action,
                "top_flags": [f.model_dump(mode="json") for f in fusion.top_flags],
            },
        )

        await _emit(on_event, "status", "WRITING")
        customer = await _customer(customer_task, check_id)
        message, explainer_ms = await self._explain(
            check, fusion, evidence, customer, deadline, tokens
        )
        total_ms = _ms(t0)

        typology = evidence.typology_guess if evidence else None
        confidence = evidence.typology_confidence if evidence else None
        case_id = new_id("case") if fusion.verdict != "GREEN" else None
        latency = LatencyMs(
            txn=check.latency_ms.txn,
            evidence=evidence_run.latency_ms if evidence_run else None,
            intel=watchlist_ms,
            explainer=explainer_ms,
            verdict=verdict_ms,
            total=total_ms,
        )
        response = CheckMessageResponse(
            check_id=check_id,
            status="DONE",
            verdict=fusion.verdict,
            action=fusion.action,
            needs_review=fusion.needs_review,
            typology=typology,
            confidence=confidence,
            top_flags=fusion.top_flags,
            customer_message=message,
            case_id=case_id,
            latency_ms=latency,
        )
        await self.state.update_check(
            check_id,
            status="DONE",
            evidence=evidence,
            intel=intel,
            fusion=fusion,
            customer_message=message,
            case_id=case_id,
            latency_ms=latency,
            tokens=_total(tokens),
        )
        if case_id:
            await self.state.create_case(
                CaseRecord(
                    case_id=case_id,
                    check_id=check_id,
                    customer_id=check.customer_id,
                    customer_name=customer.full_name if customer else check.customer_id,
                    customer_age=customer.age if customer else None,
                    amount=transfer.amount,
                    verdict=fusion.verdict,
                    typology=typology or "UNKNOWN",
                    confidence=confidence or 0.0,
                    created_at=utcnow(),
                )
            )
        await _emit(on_event, "done", "DONE", response.model_dump(mode="json", by_alias=True))

        # Analyst-facing part: web intel, then the case file. The customer already has an answer.
        outcome = AnalysisOutcome(response, fusion, intel, evidence_run, None, latency, tokens)
        if case_id:
            await self._finish_case(outcome, check, msg, quick, txn, case_id)
        outcome.pipeline_ms = _ms(t0)
        self._log_check(outcome, check_id, failures, evidence_run)
        return outcome

    async def run_check(
        self,
        req: CreateCheckRequest,
        msg: CheckMessageRequest,
        *,
        on_event: EventCallback | None = None,
        as_of: datetime | None = None,
    ) -> CheckOutcome:
        started = await self.start(req, as_of=as_of)
        if started.status != "CHECKIN":
            return CheckOutcome(started)
        return CheckOutcome(started, await self.analyse(started.check_id, msg, on_event=on_event))

    # --- steps -------------------------------------------------------------------------------

    async def _lookup(self, **entities: list[str]) -> tuple[list[WatchlistMatch], bool]:
        try:
            return await lookup_entities(self.state, **entities), True
        except Exception:
            log.exception("watchlist_lookup_failed")
            return [], False

    async def _explain(
        self,
        check: CheckRecord,
        fusion: FusionResult,
        evidence: EvidenceAnalysis | None,
        customer: Customer | None,
        deadline: float,
        tokens: dict[str, TokenUsage],
    ) -> tuple[CustomerMessage, int | None]:
        contact = customer.trusted_contact_name if customer else None
        if fusion.verdict == "GREEN":
            return green_message(check.language), None
        static = static_message(fusion.verdict, check.language, fusion, trusted_contact=contact)
        remaining = min(deadline - time.perf_counter(), self.settings.explainer_budget_seconds)
        if remaining < MIN_EXPLAINER_SECONDS:
            log.warning("explainer_skipped_no_budget", check_id=check.check_id)
            return static, None
        req = ExplainRequest(
            fusion=fusion,
            language=check.language,
            typology=evidence.typology_guess if evidence else "UNKNOWN",
            age=customer.age if customer else None,
            trusted_contact=contact,
            check_id=check.check_id,
        )
        t = time.perf_counter()
        try:
            run = await asyncio.wait_for(self.explainer.explain(req), remaining)
        except Exception as e:  # timeout or a bug: the static message for this verdict
            log.warning("explainer_failed", check_id=check.check_id, error=type(e).__name__)
            return static, _ms(t)
        if run.called_model:
            tokens["explainer"] = run.tokens
        return run.message, run.latency_ms if run.called_model else None

    async def _finish_case(
        self,
        outcome: AnalysisOutcome,
        check: CheckRecord,
        msg: CheckMessageRequest,
        quick: Entities,
        txn: TxnRisk,
        case_id: str,
    ) -> None:
        """Web intel ∥ case file, each inside CASEFILE_TIMEOUT_SECONDS. The case file uses the
        watchlist intel and is saved as soon as it is ready (a grounded search can take 10-20 s);
        the web findings then land on the check for the console's Intel tab."""
        budget = self.settings.casefile_timeout_seconds
        evidence = outcome.evidence.analysis if outcome.evidence else None
        cf_req = CaseFileRequest(
            transfer=check.transfer,
            txn=txn,
            fusion=outcome.fusion,
            evidence=evidence,
            intel=outcome.intel,
            customer_text=msg.text,
            quick_reply=msg.quick_reply,
            check_id=check.check_id,
        )
        intel_task = asyncio.create_task(self._web_intel(outcome, check, quick, evidence, budget))

        t = time.perf_counter()
        try:
            cf_run = await asyncio.wait_for(self.casefile.write(cf_req), budget)
            case_file = cf_run.case_file
            outcome.tokens["casefile"] = cf_run.tokens
        except Exception as e:  # timeout or a bug: the deterministic case file
            log.warning("casefile_failed", check_id=check.check_id, error=type(e).__name__)
            case_file = fallback_case_file(cf_req)
        outcome.case_file = case_file
        outcome.latency.casefile = _ms(t)
        await self.state.update_case(case_id, case_file=case_file)

        search_ms = await intel_task
        outcome.latency.intel = (outcome.latency.intel or 0) + search_ms
        await self.state.update_check(
            check.check_id,
            intel=outcome.intel,
            latency_ms=outcome.latency,
            tokens=_total(outcome.tokens),
        )

    async def _web_intel(
        self,
        outcome: AnalysisOutcome,
        check: CheckRecord,
        quick: Entities,
        evidence: EvidenceAnalysis | None,
        budget: float,
    ) -> int:
        """The Scam-Intel agent on the unknown sites and platforms; updates outcome.intel."""
        if evidence is None:
            return 0
        req = IntelRequest(
            entities=merge_entities(quick, evidence.entities),
            watchlist_matches=outcome.intel.watchlist_matches,
            typology=evidence.typology_guess,
            confidence=evidence.typology_confidence,
            claimed_sender=evidence.claimed_sender,
            summary=evidence.summary,
            check_id=check.check_id,
        )
        t = time.perf_counter()
        try:
            run = await asyncio.wait_for(self.intel.investigate(req, state=self.state), budget)
            outcome.intel = run.result
            if run.called_model:
                outcome.tokens["intel"] = run.tokens
        except Exception as e:  # timeout or a bug: keep the watchlist matches
            log.warning("intel_failed", check_id=check.check_id, error=type(e).__name__)
        return _ms(t)

    def _log_check(
        self,
        outcome: AnalysisOutcome,
        check_id: str,
        failures: list[str],
        evidence_run: EvidenceRun | None,
    ) -> None:
        r, total = outcome.response, _total(outcome.tokens)
        log.info(
            "check_done",
            check_id=check_id,
            verdict=r.verdict,
            action=r.action,
            needs_review=r.needs_review,
            typology=r.typology,
            confidence=r.confidence,
            flags=[f.code for f in r.top_flags],
            watchlist_matches=len(outcome.intel.watchlist_matches),
            web_findings=len(outcome.intel.web_findings),
            case_id=r.case_id,
            latency_ms=outcome.latency.model_dump(exclude_none=True),
            pipeline_ms=outcome.pipeline_ms,
            tokens={
                **{k: {"in": v.in_, "out": v.out} for k, v in outcome.tokens.items()},
                "total": {"in": total.in_, "out": total.out},
            },
            evidence_attempts=evidence_run.attempts if evidence_run else 0,
            failures=failures,
        )


async def _emit(
    on_event: EventCallback | None,
    type_: ProgressEventType,
    stage: ProgressStage | None = None,
    data: dict[str, object] | None = None,
) -> None:
    """Progress for SSE/polling. A failing listener never breaks the check."""
    if on_event is None:
        return
    try:
        result = on_event(ProgressEvent(type=type_, stage=stage, data=data))
        if inspect.isawaitable(result):
            await result
    except Exception:
        log.exception("progress_event_failed", type=type_, stage=stage)


async def _customer(task: asyncio.Task[Customer | None], check_id: str) -> Customer | None:
    try:
        return await task
    except Exception:
        log.exception("customer_lookup_failed", check_id=check_id)
        return None


def _dedupe(matches: list[WatchlistMatch]) -> list[WatchlistMatch]:
    out: dict[tuple[str, str], WatchlistMatch] = {}
    for m in matches:
        out.setdefault((m.type, m.value), m)
    return list(out.values())


# ---------------------------------------------------------------------------------------------
# CLI: python -m app.agents.orchestrator --scenario tan|raj|aisyah|all [--runs N]
# ---------------------------------------------------------------------------------------------


async def _cli_state(settings: Settings) -> StateRepo:
    """The Firestore emulator when it runs (seeded if empty), else memory seeded from data/seed."""
    from app.data import get_state_repo
    from app.data.memory_repo import MemoryStateRepo
    from app.data.seed import emulator_up, seed_state

    state: StateRepo
    host = settings.firestore_emulator_host
    if settings.state_backend == "firestore" and host and emulator_up(host):
        state, where = get_state_repo(settings), f"Firestore emulator ({host})"
    else:
        state, where = MemoryStateRepo(), "memory (start `make emulators` to persist)"
    if await state.get_watchlist("ACCOUNT", "123-45678-9") is None:
        await seed_state(state)
    print(f"# state: {where}", file=sys.stderr)
    return state


def _print_outcome(key: str, outcome: CheckOutcome) -> None:
    started, a = outcome.started, outcome.analysis
    print(f"\n=== {key}: {outcome.verdict} ===")
    print(f"txn score {started.txn_risk.score if started.txn_risk else '-'}", end="")
    if a is None:
        print(" (GREEN fast path, no check-in)")
    else:
        r = a.response
        print(
            f" · action {r.action} · needs_review {r.needs_review} · typology {r.typology} "
            f"({r.confidence})"
        )
        print("reasons:", *(f"  - {x}" for x in a.fusion.reasons), sep="\n")
        print("top flags:", *(f"  {i}. {f.code} ({f.severity}) box={f.box_2d} “{f.quote}”"
                              for i, f in enumerate(r.top_flags, 1)), sep="\n")  # fmt: skip
    m = outcome.customer_message
    if m:
        print(f"\n[customer message, {m.language}]\n{m.headline}\n{m.body}")
        for i, e in enumerate(m.flag_explanations, 1):
            print(f"  {i}. {e.text}")
        print("next steps:", " | ".join(m.next_steps))
    if a and a.case_file:
        c = a.case_file
        print(f"\n[case file] {c.title}\n{c.summary}")
        print("timeline:", *(f"  - {x}" for x in c.timeline), sep="\n")
        print("evidence:", *(f"  - {p.flag} [{p.evidence_index}] “{p.quote}”"
                             for p in c.evidence_points), sep="\n")  # fmt: skip
        print("intel:", *(f"  - {x}" for x in c.intel_points), sep="\n")
        print(f"recommend: {c.recommended_action} ({c.confidence:.2f}) {c.recommended_reason}")
    if a:
        t = _total(a.tokens)
        print(
            f"\nlatency ms {a.latency.model_dump(exclude_none=True)} · pipeline {a.pipeline_ms}"
            f" · tokens in {t.in_} out {t.out}"
        )


async def _main(argv: list[str] | None = None) -> int:
    from app.agents.scenarios import SCENARIOS
    from app.data import get_transaction_repo

    p = argparse.ArgumentParser(prog="python -m app.agents.orchestrator")
    p.add_argument("--scenario", required=True, choices=[*SCENARIOS, "all"])
    p.add_argument("--runs", type=int, default=1, help="repeat to measure latency")
    args = p.parse_args(argv)

    settings = get_settings()
    settings.export_sdk_env()
    orch = Orchestrator(
        txn_repo=get_transaction_repo(settings), state=await _cli_state(settings), settings=settings
    )
    keys = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    totals: list[int] = []
    verdicts: list[int] = []
    unexpected = []
    for _ in range(args.runs):
        for key in keys:
            sc = SCENARIOS[key]
            outcome = await orch.run_check(sc.create_request(), sc.message())
            _print_outcome(key, outcome)
            if outcome.analysis:
                totals.append(outcome.analysis.latency.total or 0)
                verdicts.append(outcome.analysis.latency.verdict or 0)
            if outcome.verdict not in sc.expected:
                unexpected.append(f"{key}: {outcome.verdict} (expected {'/'.join(sc.expected)})")
    if totals:
        print(
            f"\n# customer-facing latency over {len(totals)} check(s), answer -> full result: "
            f"p50 {statistics.median(totals):.0f} ms · max {max(totals)} ms · {sorted(totals)}"
            f"\n# answer -> verdict: p50 {statistics.median(verdicts):.0f} ms · {sorted(verdicts)}"
        )
    for u in unexpected:
        print(f"# UNEXPECTED {u}", file=sys.stderr)
    return 1 if unexpected else 0


if __name__ == "__main__":
    from app.log import configure_logging

    configure_logging(get_settings().log_level, stream=sys.stderr)
    raise SystemExit(asyncio.run(_main()))
