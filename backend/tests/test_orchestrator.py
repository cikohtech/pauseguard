"""Orchestrator end to end with fake models: the GREEN fast path, the three demo shapes (RED,
AMBER, GREEN after a check-in), safe failure (timeouts, model failures, watchlist outage), a slow
explainer never downgrading RED, progress events, persistence and the case file."""

from __future__ import annotations

import re
from typing import Any

import pytest

from app.agents import orchestrator as orch_mod
from app.agents.casefile_agent import CaseFileAgent
from app.agents.evidence_agent import EvidenceAgent
from app.agents.explainer_agent import ExplainerAgent, static_message
from app.agents.intel_agent import IntelAgent
from app.agents.orchestrator import CheckStateError, Orchestrator, checkin_question, new_id
from app.agents.scenarios import SCENARIOS
from app.config import Settings
from app.data.base import NotFoundError
from app.data.memory_repo import MemoryStateRepo
from app.data.seed import seed_state
from app.data.sqlite_repo import SqliteTransactionRepo
from app.models.schemas import (
    CheckMessageRequest,
    CreateCheckRequest,
    ProgressEvent,
    Transfer,
)
from tests.conftest import AS_OF
from tests.fakes import FakeLlm, call, fake, grounded, request_text

MAS_REQ = "mas-gov-verify.example (claims to be the Monetary Authority of Singapore)"


def settings(**kw: Any) -> Settings:
    base = {"agent_timeout_seconds": 5.0, "casefile_timeout_seconds": 5.0}
    return Settings(_env_file=None, **(base | kw))  # type: ignore[call-arg]


@pytest.fixture
async def state() -> MemoryStateRepo:
    repo = MemoryStateRepo()
    await seed_state(repo)
    return repo


def evidence(typology: str, conf: float, flags: list[dict[str, Any]], **kw: Any) -> dict[str, Any]:
    return {
        "evidence_present": True,
        "summary": f"{typology} evidence.",
        "red_flags": flags,
        "typology_guess": typology,
        "typology_confidence": conf,
        "language_detected": "en",
        "injection_attempt_detected": False,
    } | kw


def boxed(code: str, quote: str, box: list[int]) -> dict[str, Any]:
    return {"code": code, "severity": "HIGH", "quote": quote, "evidence_index": 0, "box_2d": box}


TAN_EVIDENCE = evidence(
    "GOV_OFFICIAL_IMPERSONATION",
    0.99,
    [
        boxed("SAFE_ACCOUNT", "转到金管局的安全账户", [495, 52, 517, 750]),
        boxed("AUTHORITY_CLAIM", "我是MAS的李伟", [209, 218, 229, 755]),
    ],
    claimed_sender={"name": "Lee Wei", "claimed_org": "MAS", "channel": "WhatsApp"},
    entities={
        "phones": ["+65 8000 0147"],
        "urls": ["https://mas-gov-verify.example/case/2231"],
        "orgs": ["MAS"],
    },
)
RAJ_EVIDENCE = evidence(
    "JOB_TASK",
    0.95,
    [
        {"code": "PAY_TO_EARN", "severity": "HIGH", "quote": "top up S$450", "evidence_index": 0},
        {"code": "URGENCY", "severity": "MEDIUM", "quote": "Gold slots are limited today"},
    ],
)
AISYAH_EVIDENCE = evidence("NONE", 0.95, [])
CASE_ANSWER = {
    "title": "MAS impersonation, safe account",
    "summary": "A fake MAS officer. Unknown: earlier transfers.",
    "timeline": ["Contacted on WhatsApp"],
    "evidence_points": [{"flag": "SAFE_ACCOUNT", "quote": "x"}],
    "intel_points": ["Phone reported 6 times"],
    "recommended_action": "REPORT_SCAM",
    "recommended_reason": "Conclusive.",
    "confidence": 0.98,
}


def build(
    state: MemoryStateRepo,
    repo: SqliteTransactionRepo,
    *,
    ev: tuple[Any, ...] = (),
    intel: tuple[Any, ...] = (),
    search: tuple[Any, ...] = (),
    explain: tuple[Any, ...] = (),
    case: tuple[Any, ...] = (),
    cfg: Settings | None = None,
    slow: dict[str, float] | None = None,
) -> tuple[Orchestrator, dict[str, FakeLlm]]:
    """Real agents with fake models; `slow` delays a model's answers, e.g. {"ev": 1.0}."""
    s, slow = cfg or settings(), slow or {}
    llms = {
        "ev": fake(*ev, delay=slow.get("ev", 0.0)),
        "intel": fake(*intel, schema_with_tools=True),
        "search": fake(*search),
        "explain": fake(*explain, delay=slow.get("explain", 0.0)),
        "case": fake(*case, delay=slow.get("case", 0.0)),
    }
    o = Orchestrator(
        txn_repo=repo,
        state=state,
        settings=s,
        evidence=EvidenceAgent(llms["ev"], s),
        intel=IntelAgent(llms["intel"], s, search_model=llms["search"]),
        explainer=ExplainerAgent(llms["explain"], s),
        casefile=CaseFileAgent(llms["case"], s),
    )
    return o, llms


async def start(o: Orchestrator, key: str) -> str:
    started = await o.start(SCENARIOS[key].create_request(), as_of=AS_OF)
    assert started.status == "CHECKIN"
    return started.check_id


# --- start -------------------------------------------------------------------------------


async def test_low_risk_known_payee_is_green_at_once(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, llms = build(state, sqlite_repo)
    req = CreateCheckRequest(
        customer_id="cust_003",
        transfer=Transfer(payee_name="Salmah Ismail", account_number="358-12413-4", amount=60),
    )
    r = await o.start(req, as_of=AS_OF)
    assert r.status == "DONE" and r.verdict == "GREEN" and r.question is None
    assert r.customer_message and r.customer_message.headline == "Looks good"
    assert r.txn_risk and r.txn_risk.score < 30
    check = await state.get_check(r.check_id)
    assert check and check.status == "DONE" and check.fusion and check.fusion.verdict == "GREEN"
    assert check.latency_ms.total is not None and check.messages == []
    assert all(llm.requests == [] for llm in llms.values())


async def test_tan_starts_with_a_chinese_check_in_and_the_watchlist_hit(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, _ = build(state, sqlite_repo)
    r = await o.start(SCENARIOS["tan"].create_request(), as_of=AS_OF)
    assert r.status == "CHECKIN" and r.question == checkin_question("zh")
    assert r.txn_risk and "WATCHLIST_MATCH" in [x.code for x in r.txn_risk.reasons]
    check = await state.get_check(r.check_id)
    assert check and check.language == "zh" and check.messages[0].role == "assistant"


async def test_language_defaults_to_the_customers_preference(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, _ = build(state, sqlite_repo)
    req = SCENARIOS["tan"].create_request().model_copy(update={"language": None})
    r = await o.start(req, as_of=AS_OF)
    assert r.question and r.question.text == checkin_question("zh").text


# --- analyse: the three demo shapes ------------------------------------------------------


async def test_tan_is_red_with_case_file_intel_and_events(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, llms = build(
        state,
        sqlite_repo,
        ev=(TAN_EVIDENCE,),
        intel=(
            call("search_agent", request=MAS_REQ),
            {"web_findings": [{"query": MAS_REQ, "finding": "Not MAS.", "risk": "HIGH"}]},
        ),
        search=(grounded("No record; MAS is mas.gov.sg.", ["https://g.example/1"]),),
        explain=({"headline": "为保护您，转账已暂停", "body": "真正的官员绝不会要求您转账。"},),
        case=(CASE_ANSWER,),
    )
    check_id = await start(o, "tan")
    events: list[ProgressEvent] = []
    out = await o.analyse(check_id, SCENARIOS["tan"].message(), on_event=events.append)

    r = out.response
    assert r.verdict == "RED" and r.action == "HOLD_FOR_REVIEW" and not r.needs_review
    assert r.typology == "GOV_OFFICIAL_IMPERSONATION" and r.case_id
    codes = [f.code for f in r.top_flags]
    assert codes == ["SAFE_ACCOUNT", "AUTHORITY_CLAIM", "WATCHLIST_MATCH", "WATCHLIST_MATCH"]
    assert r.customer_message and r.customer_message.headline == "为保护您，转账已暂停"
    assert r.customer_message.next_steps[1] == "打电话给Tan Jun Hao (son)"
    assert {(m.type, m.value) for m in out.intel.watchlist_matches} == {
        ("ACCOUNT", "123456789"),
        ("PHONE", "+6580000147"),
    }
    assert [(e.type, e.stage) for e in events] == [
        ("status", "ANALYSING_EVIDENCE"),
        ("status", "CHECKING_INTEL"),
        ("partial", "ANALYSING_EVIDENCE"),
        ("partial", "CHECKING_INTEL"),
        ("status", "DECIDING"),
        ("partial", "DECIDING"),
        ("status", "WRITING"),
        ("done", "DONE"),
    ]
    assert events[5].data and events[5].data["verdict"] == "RED"
    assert events[-1].data and events[-1].data["case_id"] == r.case_id

    # Analyst side: web intel (grounded) and the case file, persisted.
    assert out.case_file and out.case_file.recommended_action == "REPORT_SCAM"
    assert [f.sources for f in out.intel.web_findings] == [["https://g.example/1"]]
    check = await state.get_check(check_id)
    assert check and check.status == "DONE" and check.case_id == r.case_id
    assert [m.role for m in check.messages] == ["assistant", "customer"]
    assert check.intel and check.intel.web_findings and check.tokens.in_ > 0
    assert check.latency_ms.casefile is not None and check.latency_ms.verdict is not None
    case = await state.get_case(r.case_id)
    assert case and case.customer_name == "Tan Mei Ling" and case.customer_age == 67
    assert case.case_file == out.case_file and case.status == "OPEN" and case.amount == 8000
    assert set(out.tokens) == {"evidence", "explainer", "intel", "casefile"}
    assert "政府官员" in request_text(llms["ev"].requests[0])


async def test_raj_pasted_chat_is_amber(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, llms = build(
        state,
        sqlite_repo,
        ev=(RAJ_EVIDENCE,),
        explain=(
            {"headline": "This looks like a job scam", "body": "Real jobs never ask you to pay."},
        ),
        case=(CASE_ANSWER | {"recommended_action": "HOLD"},),
    )
    check_id = await start(o, "raj")
    out = await o.analyse(check_id, SCENARIOS["raj"].message())
    r = out.response
    assert r.verdict == "AMBER" and r.action == "COOL_OFF" and r.case_id and not r.needs_review
    assert r.customer_message and r.customer_message.next_steps[0] == "Pause for 24 hours"
    sent = request_text(llms["ev"].requests[0])
    assert '<evidence index="0" type="text">' in sent and "TaskStar" in sent
    assert llms["intel"].requests == []  # nothing unknown to search
    case = await state.get_case(r.case_id)
    assert case and case.verdict == "AMBER" and case.case_file


async def test_aisyah_tenancy_is_green_without_explainer_or_case(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, llms = build(state, sqlite_repo, ev=(AISYAH_EVIDENCE,))
    check_id = await start(o, "aisyah")
    out = await o.analyse(check_id, SCENARIOS["aisyah"].message())
    r = out.response
    assert r.verdict == "GREEN" and r.case_id is None and out.case_file is None
    assert r.customer_message and r.customer_message.headline == "Looks good"
    assert llms["explain"].requests == [] and llms["case"].requests == []
    assert await state.list_cases() == []
    assert out.latency.explainer is None and out.latency.total is not None


# --- safe failure ------------------------------------------------------------------------


async def test_evidence_timeout_is_amber_with_review(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, llms = build(
        state,
        sqlite_repo,
        ev=(RAJ_EVIDENCE,),
        case=("bad", "bad"),
        cfg=settings(agent_timeout_seconds=0.2),
        slow={"ev": 1.0},
    )
    check_id = await start(o, "raj")
    out = await o.analyse(check_id, SCENARIOS["raj"].message())
    r = out.response
    assert r.verdict == "AMBER" and r.needs_review and r.typology is None
    assert r.customer_message and "review" in r.customer_message.body
    assert llms["explain"].requests == []  # nothing to explain: the static review message
    assert out.case_file and out.case_file.recommended_action == "ESCALATE"  # fallback file


async def test_evidence_model_failure_is_amber_with_review(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, _ = build(state, sqlite_repo, ev=("nope", "still nope"), case=(CASE_ANSWER,))
    check_id = await start(o, "aisyah")
    out = await o.analyse(check_id, SCENARIOS["aisyah"].message())
    assert out.response.verdict == "AMBER" and out.response.needs_review


async def test_watchlist_outage_during_analysis_needs_review(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    o, _ = build(state, sqlite_repo, ev=(AISYAH_EVIDENCE,), case=(CASE_ANSWER,))
    check_id = await start(o, "aisyah")

    async def down(*_: Any, **__: Any) -> None:
        raise RuntimeError("Firestore unavailable")

    monkeypatch.setattr(state, "get_watchlist", down)
    out = await o.analyse(check_id, SCENARIOS["aisyah"].message())
    assert out.response.verdict == "AMBER" and out.response.needs_review


async def test_a_slow_explainer_never_downgrades_red(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(orch_mod, "MIN_EXPLAINER_SECONDS", 0.05)
    o, _ = build(
        state,
        sqlite_repo,
        ev=(TAN_EVIDENCE,),
        explain=({"headline": "h", "body": "b"},),
        case=(CASE_ANSWER,),
        cfg=settings(agent_timeout_seconds=0.3),
        slow={"explain": 2.0},
    )
    check_id = await start(o, "tan")
    out = await o.analyse(check_id, SCENARIOS["tan"].message(evidence_uris=()))
    r = out.response
    assert r.verdict == "RED" and not r.needs_review
    assert r.customer_message == static_message(
        "RED", "zh", out.fusion, trusted_contact="Tan Jun Hao (son)"
    )


async def test_no_budget_left_skips_the_explainer(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, llms = build(
        state,
        sqlite_repo,
        ev=(TAN_EVIDENCE,),
        case=(CASE_ANSWER,),
        cfg=settings(agent_timeout_seconds=0.5),
    )
    check_id = await start(o, "tan")
    out = await o.analyse(check_id, SCENARIOS["tan"].message())
    assert out.response.verdict == "RED" and llms["explain"].requests == []


async def test_a_slow_case_file_gets_the_fallback(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, _ = build(
        state,
        sqlite_repo,
        ev=(RAJ_EVIDENCE,),
        explain=({"headline": "h", "body": "b"},),
        case=(CASE_ANSWER,),
        cfg=settings(casefile_timeout_seconds=0.2),
        slow={"case": 2.0},
    )
    check_id = await start(o, "raj")
    out = await o.analyse(check_id, SCENARIOS["raj"].message())
    assert out.case_file and "fallback" in out.case_file.recommended_reason
    case = await state.get_case(out.response.case_id or "")
    assert case and case.case_file == out.case_file


# --- contract ----------------------------------------------------------------------------


async def test_a_check_is_analysed_once_and_must_exist(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, _ = build(state, sqlite_repo, ev=(AISYAH_EVIDENCE,))
    check_id = await start(o, "aisyah")
    await o.analyse(check_id, CheckMessageRequest(text="deposit"))
    with pytest.raises(CheckStateError):
        await o.analyse(check_id, CheckMessageRequest(text="again"))
    with pytest.raises(NotFoundError):
        await o.analyse("chk_missing", CheckMessageRequest(text="x"))


async def test_a_failing_listener_does_not_break_the_check(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, _ = build(state, sqlite_repo, ev=(AISYAH_EVIDENCE,))
    check_id = await start(o, "aisyah")
    seen: list[str] = []

    async def listener(e: ProgressEvent) -> None:
        seen.append(e.type)
        raise RuntimeError("SSE client went away")

    out = await o.analyse(check_id, SCENARIOS["aisyah"].message(), on_event=listener)
    assert out.response.verdict == "GREEN" and seen[-1] == "done"


async def test_run_check_covers_both_paths(
    state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    o, _ = build(state, sqlite_repo, ev=(AISYAH_EVIDENCE,))
    sc = SCENARIOS["aisyah"]
    full = await o.run_check(sc.create_request(), sc.message(), as_of=AS_OF)
    assert full.analysis and full.verdict == "GREEN" and full.customer_message
    fast = await o.run_check(
        CreateCheckRequest(
            customer_id="cust_003",
            transfer=Transfer(payee_name="Salmah Ismail", account_number="358-12413-4", amount=60),
        ),
        CheckMessageRequest(text="unused"),
        as_of=AS_OF,
    )
    assert fast.analysis is None and fast.verdict == "GREEN" and fast.customer_message


def test_ids_are_prefixed_time_ordered_and_unique() -> None:
    ids = [new_id("chk") for _ in range(50)]
    assert all(re.fullmatch(r"chk_[0-9A-HJKMNP-TV-Z]{26}", i) for i in ids)
    assert len(set(ids)) == 50 and ids[0][:10] <= ids[-1][:10]


def test_message_request_allows_three_evidence_items_in_total() -> None:
    CheckMessageRequest(evidence_uris=["a", "b"], pasted_text="chat")
    with pytest.raises(ValueError, match="At most 3"):
        CheckMessageRequest(evidence_uris=["a", "b", "c"], pasted_text="chat")
