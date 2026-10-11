"""Every API route over HTTP (httpx + the ASGI app): auth, the three demo flows, uploads, SSE,
safe failure (timeout/crash -> AMBER + review), choices, cases + REPORT_SCAM, metrics, admin.
Agents are stubs (tests/api_support.py); the orchestrator's own logic is real."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.agents.scenarios import SCENARIOS
from app.api import analysis as analysis_mod
from app.api import checks as checks_mod
from app.api import uploads as uploads_mod
from app.api.deps import Services
from app.data.base import utcnow
from app.data.memory_repo import MemoryStateRepo
from app.data.seed import seed_state
from app.data.sqlite_repo import SqliteTransactionRepo
from app.models.schemas import CheckAnalyticsRow, CheckMessageRequest, Transfer
from tests.api_support import (
    ADMIN,
    ANALYST,
    CUSTOMER,
    PinnedOrchestrator,
    StubEvidence,
    build_services,
    client_for,
    make_settings,
    sse_events,
)

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


@pytest.fixture
async def state(seed_dir: Path) -> MemoryStateRepo:
    repo = MemoryStateRepo()
    await seed_state(repo, seed_dir)
    return repo


@pytest.fixture
def services(
    tmp_path: Path, state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> Services:
    return build_services(tmp_path, state, sqlite_repo)


@pytest.fixture
async def client(services: Services) -> AsyncIterator[httpx.AsyncClient]:
    async with client_for(services) as c:
        yield c
    await services.drain()


def create_body(key: str) -> dict[str, Any]:
    return SCENARIOS[key].create_request().model_dump(mode="json")


def message_body(key: str, evidence_uris: list[str] | None = None) -> dict[str, Any]:
    msg = SCENARIOS[key].message(evidence_uris=tuple(evidence_uris or ()))
    return msg.model_dump(mode="json", exclude_none=True)


async def start(client: httpx.AsyncClient, key: str) -> dict[str, Any]:
    r = await client.post("/api/v1/checks", json=create_body(key), headers=CUSTOMER)
    assert r.status_code == 201, r.text
    return r.json()


async def upload(client: httpx.AsyncClient, check_id: str, name: str = "chat.png") -> str:
    r = await client.post(
        "/api/v1/uploads/sign",
        json={"check_id": check_id, "filename": name, "content_type": "image/png"},
        headers=CUSTOMER,
    )
    assert r.status_code == 200, r.text
    signed = r.json()
    put = await client.put(signed["upload_url"], content=PNG, headers=signed["headers"])
    assert put.status_code == 200, put.text
    return str(signed["gcs_uri"])


async def run(client: httpx.AsyncClient, key: str, *, with_upload: bool = True) -> dict[str, Any]:
    """start -> (upload) -> answer, as the customer app does."""
    check_id = (await start(client, key))["check_id"]
    uris = [await upload(client, check_id)] if with_upload and key != "raj" else []
    r = await client.post(
        f"/api/v1/checks/{check_id}/messages", json=message_body(key, uris), headers=CUSTOMER
    )
    assert r.status_code == 200, r.text
    return r.json()


def error_code(r: httpx.Response) -> str:
    return str(r.json()["error"]["code"])


# --- auth ------------------------------------------------------------------------------------


async def test_customer_routes_need_a_firebase_token(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/checks", json=create_body("tan"))
    assert r.status_code == 401 and error_code(r) == "UNAUTHORIZED"
    bad = await client.post(
        "/api/v1/checks", json=create_body("tan"), headers={"Authorization": "Bearer nope"}
    )
    assert (
        bad.status_code == 401 and bad.json()["error"]["message"] == "Invalid or expired ID token"
    )


async def test_analyst_routes_need_the_analyst_claim(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/v1/cases")).status_code == 401
    r = await client.get("/api/v1/cases", headers=CUSTOMER)
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"
    assert (await client.get("/api/v1/cases", headers=ANALYST)).status_code == 200
    assert (await client.get("/api/v1/metrics", headers=CUSTOMER)).status_code == 403


async def test_admin_token_passes_every_route_and_a_wrong_one_is_refused(
    client: httpx.AsyncClient,
) -> None:
    assert (await client.get("/api/v1/cases", headers=ADMIN)).status_code == 200
    assert (await client.post("/api/v1/checks", json=create_body("tan"), headers=ADMIN)).is_success
    r = await client.get("/api/v1/cases", headers={"X-Admin-Token": "guess"})
    assert r.status_code == 403 and error_code(r) == "FORBIDDEN"


async def test_auth_disabled_lets_local_dev_in_as_an_analyst(
    tmp_path: Path, state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    s = make_settings(tmp_path, auth_disabled=True)
    svc = build_services(tmp_path, state, sqlite_repo, settings=s)
    async with client_for(svc) as c:
        assert (await c.get("/api/v1/cases")).status_code == 200
        assert (await c.post("/api/v1/checks", json=create_body("tan"))).status_code == 201
    await svc.drain()


async def test_sse_route_accepts_the_token_as_a_query_parameter(client: httpx.AsyncClient) -> None:
    check_id = (await start(client, "tan"))["check_id"]
    assert (await client.get(f"/api/v1/checks/{check_id}")).status_code == 401
    r = await client.get(f"/api/v1/checks/{check_id}?access_token=anon-token")
    assert r.status_code == 200 and r.json()["status"] == "CHECKIN"


# --- POST /checks ----------------------------------------------------------------------------


async def test_tan_starts_a_chinese_check_in(client: httpx.AsyncClient) -> None:
    body = await start(client, "tan")
    assert body["status"] == "CHECKIN" and body["check_id"].startswith("chk_")
    assert body["question"]["text"] == "这笔转账是谁让您付的？有人先联系您吗？"
    assert len(body["question"]["quick_replies"]) == 6
    assert "WATCHLIST_MATCH" in [x["code"] for x in body["txn_risk"]["reasons"]]
    assert body["verdict"] is None and body["customer_message"] is None


async def test_low_risk_is_green_at_once_and_recorded_in_analytics(
    client: httpx.AsyncClient, services: Services
) -> None:
    req = {
        "customer_id": "cust_003",
        "transfer": {"payee_name": "Salmah Ismail", "account_number": "358-12413-4", "amount": 60},
    }
    r = await client.post("/api/v1/checks", json=req, headers=CUSTOMER)
    body = r.json()
    assert r.status_code == 201 and body["status"] == "DONE" and body["verdict"] == "GREEN"
    assert body["customer_message"]["headline"] == "Looks good" and body["question"] is None
    await services.drain()
    (row,) = services.analytics.latest_rows(utcnow().replace(year=2000))
    assert row.check_id == body["check_id"] and row.verdict == "GREEN" and row.fast_path
    assert row.model is None and row.tokens_in == 0


async def test_unknown_customer_and_bad_body_are_validation_errors(
    client: httpx.AsyncClient,
) -> None:
    r = await client.post(
        "/api/v1/checks", json={**create_body("tan"), "customer_id": "cust_999"}, headers=CUSTOMER
    )
    assert r.status_code == 422 and error_code(r) == "VALIDATION_ERROR"
    assert "cust_999" in r.json()["error"]["message"]
    body = create_body("tan")
    body["transfer"]["amount"] = -5
    r = await client.post("/api/v1/checks", json=body, headers=CUSTOMER)
    err = r.json()["error"]
    assert r.status_code == 422 and err["code"] == "VALIDATION_ERROR"
    assert err["message"].startswith("transfer.amount:")
    assert err["details"][0]["loc"] == ["body", "transfer", "amount"]
    assert "input" not in err["details"][0]  # the request is never echoed back


async def test_rate_limit_per_ip_and_per_customer(
    tmp_path: Path, state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    s = make_settings(tmp_path, rate_limit_checks="2/hour", rate_limit_checks_per_customer="3/hour")
    svc = build_services(tmp_path, state, sqlite_repo, settings=s)
    async with client_for(svc) as c:
        for _ in range(2):
            assert (
                await c.post("/api/v1/checks", json=create_body("tan"), headers=CUSTOMER)
            ).is_success
        r = await c.post("/api/v1/checks", json=create_body("raj"), headers=CUSTOMER)
        assert r.status_code == 429 and error_code(r) == "RATE_LIMITED"
        assert "per ip" in r.json()["error"]["message"]
        # Behind Cloud Run's front end, the client IP is the right-most X-Forwarded-For entry.
        # Another IP has its own budget, but
        # the customer's budget is shared: 2 used + 1 = 3, then the customer limit trips.
        assert svc.limiter is not None
        svc.limiter.behind_proxy = True
        other = {**CUSTOMER, "X-Forwarded-For": "6.6.6.6, 203.0.113.9"}
        assert (await c.post("/api/v1/checks", json=create_body("tan"), headers=other)).is_success
        r = await c.post("/api/v1/checks", json=create_body("tan"), headers=other)
        assert r.status_code == 429 and "per customer" in r.json()["error"]["message"]
        # Service callers (smoke test, benchmark) are never limited.
        assert (await c.post("/api/v1/checks", json=create_body("tan"), headers=ADMIN)).is_success
    await svc.drain()


async def test_benchmark_traffic_is_marked_only_with_the_admin_token(
    client: httpx.AsyncClient, services: Services
) -> None:
    flagged = {"X-PauseGuard-Eval": "true"}
    a = (
        await client.post("/api/v1/checks", json=create_body("tan"), headers=ADMIN | flagged)
    ).json()
    b = (
        await client.post("/api/v1/checks", json=create_body("tan"), headers=CUSTOMER | flagged)
    ).json()
    check_a = await services.state.get_check(a["check_id"])
    check_b = await services.state.get_check(b["check_id"])
    assert check_a and check_a.is_eval and check_b and not check_b.is_eval


# --- the three demo flows --------------------------------------------------------------------


async def test_tan_upload_and_answer_is_red_with_a_case(
    client: httpx.AsyncClient, services: Services
) -> None:
    check_id = (await start(client, "tan"))["check_id"]
    uri = await upload(client, check_id, "WhatsApp chat (1).png")
    assert uri.endswith(f"/checks/{check_id}/0-WhatsApp_chat_1.png")
    r = await client.post(
        f"/api/v1/checks/{check_id}/messages", json=message_body("tan", [uri]), headers=CUSTOMER
    )
    body = r.json()
    assert r.status_code == 200 and body["status"] == "DONE"
    assert body["verdict"] == "RED" and body["action"] == "HOLD_FOR_REVIEW"
    assert body["typology"] == "GOV_OFFICIAL_IMPERSONATION" and body["case_id"].startswith("case_")
    assert body["top_flags"][0]["box_2d"] == [495, 52, 517, 750]
    assert body["customer_message"]["language"] == "zh"
    assert body["latency_ms"]["total"] is not None and body["latency_ms"]["verdict"] is not None

    evidence = services.orchestrator.evidence
    assert isinstance(evidence, StubEvidence)
    (req,) = evidence.requests
    assert [i.uri for i in req.items] == [uri] and req.items[0].kind == "image"
    saved = services.settings.local_uploads_dir / "checks" / check_id / "0-WhatsApp_chat_1.png"
    assert saved.read_bytes() == PNG

    check = (await client.get(f"/api/v1/checks/{check_id}", headers=CUSTOMER)).json()
    assert check["status"] == "DONE" and check["uploads"] == [uri]
    assert [m["role"] for m in check["messages"]] == ["assistant", "customer"]
    assert "case_file" not in check  # customer-safe

    await services.drain()  # the case file is written after the answer
    case = await services.state.get_case(body["case_id"])
    assert case and case.verdict == "RED" and case.case_file is not None
    (row,) = services.analytics.latest_rows(utcnow().replace(year=2000))
    assert row.verdict == "RED" and row.tokens_in == 1200 + 400 + 900 and not row.fast_path
    assert row.model == "gemini-test"


async def test_raj_pasted_chat_is_amber_and_aisyah_is_green(client: httpx.AsyncClient) -> None:
    raj = await run(client, "raj")
    assert raj["verdict"] == "AMBER" and raj["action"] == "COOL_OFF" and raj["case_id"]
    aisyah = await run(client, "aisyah")
    assert aisyah["verdict"] == "GREEN" and aisyah["case_id"] is None


async def test_answer_rules(client: httpx.AsyncClient) -> None:
    missing = await client.post(
        "/api/v1/checks/chk_00000000000000000000000000/messages",
        json={"text": "x"},
        headers=CUSTOMER,
    )
    assert missing.status_code == 404 and error_code(missing) == "NOT_FOUND"

    check_id = (await start(client, "tan"))["check_id"]
    foreign = await client.post(
        f"/api/v1/checks/{check_id}/messages",
        json={"text": "x", "evidence_uris": ["gs://someone-else/checks/chk_X/secret.png"]},
        headers=CUSTOMER,
    )
    assert foreign.status_code == 422 and "POST /uploads/sign" in foreign.json()["error"]["message"]
    too_many = await client.post(
        f"/api/v1/checks/{check_id}/messages",
        json={"evidence_uris": ["a", "b", "c"], "pasted_text": "hi"},
        headers=CUSTOMER,
    )
    assert too_many.status_code == 422

    ok = await client.post(
        f"/api/v1/checks/{check_id}/messages", json=message_body("tan"), headers=CUSTOMER
    )
    assert ok.status_code == 200
    again = await client.post(
        f"/api/v1/checks/{check_id}/messages", json=message_body("tan"), headers=CUSTOMER
    )
    assert again.status_code == 409 and error_code(again) == "CONFLICT"


# --- safe failure ----------------------------------------------------------------------------


class HangingOrchestrator(PinnedOrchestrator):
    async def analyse(self, *a: Any, **kw: Any) -> Any:
        await asyncio.sleep(3600)


class CrashingOrchestrator(PinnedOrchestrator):
    async def analyse(self, *a: Any, **kw: Any) -> Any:
        raise RuntimeError("boom")


@pytest.mark.parametrize("orch_cls", [HangingOrchestrator, CrashingOrchestrator])
async def test_timeout_or_crash_answers_amber_for_review_never_an_error(
    tmp_path: Path,
    state: MemoryStateRepo,
    sqlite_repo: SqliteTransactionRepo,
    monkeypatch: pytest.MonkeyPatch,
    orch_cls: type[PinnedOrchestrator],
) -> None:
    monkeypatch.setattr(analysis_mod, "ANALYSIS_GRACE_SECONDS", 0.0)
    s = make_settings(tmp_path, agent_timeout_seconds=0.2)
    orch = orch_cls(txn_repo=sqlite_repo, state=state, settings=s)
    svc = build_services(tmp_path, state, sqlite_repo, settings=s, orchestrator=orch)
    async with client_for(svc) as c:
        check_id = (await start(c, "aisyah"))["check_id"]
        r = await c.post(
            f"/api/v1/checks/{check_id}/messages", json=message_body("aisyah"), headers=CUSTOMER
        )
        body = r.json()
        assert r.status_code == 200
        assert body["verdict"] == "AMBER" and body["needs_review"] is True  # never GREEN
        assert body["customer_message"]["headline"] and body["case_id"]
        check = await state.get_check(check_id)
        assert check and check.status == "DONE" and check.fusion and check.fusion.needs_review
        case = await state.get_case(body["case_id"])
        assert case and case.verdict == "AMBER" and case.case_file is not None
        assert case.customer_name == "Nur Aisyah"
        events = sse_events(
            (await c.get(f"/api/v1/checks/{check_id}/events", headers=CUSTOMER)).text
        )
        assert events[-1]["event"] == "done" and events[-1]["data"]["data"]["verdict"] == "AMBER"
    await svc.drain()


# --- SSE ------------------------------------------------------------------------------------


async def test_events_stream_in_the_documented_order(
    tmp_path: Path, state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    svc = build_services(tmp_path, state, sqlite_repo, evidence=StubEvidence(delay=0.3))
    async with client_for(svc) as c:
        check_id = (await start(c, "tan"))["check_id"]
        sse, answer = await asyncio.gather(
            c.get(f"/api/v1/checks/{check_id}/events", headers=CUSTOMER),
            c.post(
                f"/api/v1/checks/{check_id}/messages", json=message_body("tan"), headers=CUSTOMER
            ),
        )
        assert sse.headers["content-type"].startswith("text/event-stream")
        events = sse_events(sse.text)
        order = [(e["event"], e["data"].get("stage")) for e in events]
        assert order == [
            ("status", "ANALYSING_EVIDENCE"),
            ("status", "CHECKING_INTEL"),
            ("partial", "ANALYSING_EVIDENCE"),
            ("partial", "CHECKING_INTEL"),
            ("status", "DECIDING"),
            ("partial", "DECIDING"),
            ("status", "WRITING"),
            ("done", "DONE"),
        ]
        assert events[5]["data"]["data"]["verdict"] == "RED"
        assert events[-1]["data"]["data"] == answer.json()
        # A finished check: `done` at once, rebuilt from the stored document.
        late = sse_events((await c.get(f"/api/v1/checks/{check_id}/events", headers=CUSTOMER)).text)
        assert [e["event"] for e in late] == ["done"]
        assert late[0]["data"]["data"]["verdict"] == "RED"
    await svc.drain()


async def test_events_fall_back_to_the_document_when_another_instance_analyses(
    client: httpx.AsyncClient, services: Services, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(checks_mod, "SSE_POLL_SECONDS", 0.05)
    check_id = (await start(client, "aisyah"))["check_id"]

    async def elsewhere() -> None:  # no events here: the check just turns DONE in Firestore
        await asyncio.sleep(0.2)
        await services.orchestrator.analyse(check_id, CheckMessageRequest(text="deposit"))

    sse, _ = await asyncio.gather(
        client.get(f"/api/v1/checks/{check_id}/events", headers=CUSTOMER), elsewhere()
    )
    events = sse_events(sse.text)
    assert [e["event"] for e in events] == ["done"]
    assert events[0]["data"]["data"]["verdict"] == "GREEN"


async def test_events_for_an_unknown_check_are_404(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/checks/chk_00000000000000000000000000/events", headers=CUSTOMER)
    assert r.status_code == 404 and error_code(r) == "NOT_FOUND"


# --- uploads -------------------------------------------------------------------------------


async def test_upload_rules(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    check_id = (await start(client, "tan"))["check_id"]
    bad_type = await client.post(
        "/api/v1/uploads/sign",
        json={"check_id": check_id, "filename": "a.gif", "content_type": "image/gif"},
        headers=CUSTOMER,
    )
    assert bad_type.status_code == 422
    sign = {"check_id": check_id, "filename": "x.exe", "content_type": "application/pdf"}
    first = (await client.post("/api/v1/uploads/sign", json=sign, headers=CUSTOMER)).json()
    assert first["gcs_uri"].endswith("/0-x.pdf") and first["expires_in"] == 600
    assert first["headers"] == {"Content-Type": "application/pdf"}

    url, headers = first["upload_url"], first["headers"]
    forged = await client.put(url.replace("sig=", "sig=0"), content=b"%PDF", headers=headers)
    assert forged.status_code == 403
    wrong = await client.put(url, content=b"x", headers={"Content-Type": "image/png"})
    assert wrong.status_code == 415 and error_code(wrong) == "VALIDATION_ERROR"
    monkeypatch.setattr(uploads_mod, "MAX_UPLOAD_BYTES", 8)
    big = await client.put(url, content=b"%PDF-1.7 too big", headers=headers)
    assert big.status_code == 413

    for _ in range(2):
        assert (await client.post("/api/v1/uploads/sign", json=sign, headers=CUSTOMER)).is_success
    fourth = await client.post("/api/v1/uploads/sign", json=sign, headers=CUSTOMER)
    assert fourth.status_code == 409 and "3 files" in fourth.json()["error"]["message"]

    unknown = await client.post(
        "/api/v1/uploads/sign", json={**sign, "check_id": "chk_00000000000000000000000000"},
        headers=CUSTOMER,
    )  # fmt: skip
    assert unknown.status_code == 404


async def test_uploads_close_after_the_check_in(client: httpx.AsyncClient) -> None:
    body = await run(client, "aisyah")
    r = await client.post(
        "/api/v1/uploads/sign",
        json={"check_id": body["check_id"], "filename": "late.png", "content_type": "image/png"},
        headers=CUSTOMER,
    )
    assert r.status_code == 409


# --- choice + feedback ----------------------------------------------------------------------


async def test_choices_respect_the_verdict(client: httpx.AsyncClient, services: Services) -> None:
    async def choose(check_id: str, choice: str, **kw: Any) -> httpx.Response:
        return await client.post(
            f"/api/v1/checks/{check_id}/choice", json={"choice": choice, **kw}, headers=CUSTOMER
        )

    pending = (await start(client, "tan"))["check_id"]
    assert (await choose(pending, "COOL_OFF")).status_code == 409  # no verdict yet

    red = (await run(client, "tan"))["check_id"]
    r = await choose(red, "PROCEEDED", confirmed=True)
    assert r.status_code == 409 and error_code(r) == "CONFLICT"
    assert (await choose(red, "CALLED_CONTACT")).json() == {
        "check_id": red,
        "customer_choice": "CALLED_CONTACT",
    }

    amber = (await run(client, "raj"))["check_id"]
    assert (await choose(amber, "PROCEEDED")).status_code == 409  # needs the confirm step
    assert (await choose(amber, "PROCEEDED", confirmed=True)).status_code == 200
    green = (await run(client, "aisyah"))["check_id"]
    assert (await choose(green, "PROCEEDED")).status_code == 200

    stored = await services.state.get_check(amber)
    assert stored and stored.customer_choice == "PROCEEDED"
    await services.drain()
    rows = {r.check_id: r for r in services.analytics.latest_rows(utcnow().replace(year=2000))}
    assert (
        rows[amber].customer_choice == "PROCEEDED" and rows[red].customer_choice == "CALLED_CONTACT"
    )


async def test_feedback_is_stored(client: httpx.AsyncClient, services: Services) -> None:
    check_id = (await run(client, "aisyah"))["check_id"]
    r = await client.post(
        f"/api/v1/checks/{check_id}/feedback",
        json={"helpful": True, "comment": "Clear"},
        headers=CUSTOMER,
    )
    assert r.status_code == 201 and r.json()["feedback_id"]
    missing = await client.post(
        "/api/v1/checks/chk_00000000000000000000000000/feedback",
        json={"helpful": False},
        headers=CUSTOMER,
    )
    assert missing.status_code == 404


# --- cases ----------------------------------------------------------------------------------


async def test_case_list_and_detail(client: httpx.AsyncClient, services: Services) -> None:
    tan = await run(client, "tan")
    raj = await run(client, "raj")
    await run(client, "aisyah")
    await services.drain()

    listed = (await client.get("/api/v1/cases?status=OPEN", headers=ANALYST)).json()
    assert {c["case_id"] for c in listed} == {tan["case_id"], raj["case_id"]}
    assert all(c["title"] for c in listed)
    assert (await client.get("/api/v1/cases?limit=1", headers=ANALYST)).json()[0]["case_id"] == raj[
        "case_id"
    ]  # newest first
    assert (await client.get("/api/v1/cases?limit=0", headers=ANALYST)).status_code == 422

    detail = (await client.get(f"/api/v1/cases/{tan['case_id']}", headers=ANALYST)).json()
    assert detail["case"]["verdict"] == "RED" and detail["case"]["case_file"]["summary"]
    assert detail["transfer"]["payee_name"] == "Lee Wei Investigation Acct"
    assert detail["txn_risk"]["score"] >= 50 and detail["fusion"]["verdict"] == "RED"
    assert detail["evidence"]["entities"]["phones"] == ["+65 8000 0147"]
    assert detail["messages"][1]["text"].startswith("他说他是金管局的官员")
    assert detail["audit"] == []
    (link,) = detail["evidence_links"]
    assert link["index"] == 0 and link["content_type"] == "image/png"
    image = await client.get(link["url"])  # signed: no auth header needed, like GCS
    assert image.status_code == 200 and image.content == PNG
    assert image.headers["content-type"] == "image/png"
    tampered = await client.get(link["url"].replace("/0-", "/1-"))
    assert tampered.status_code == 403

    missing = await client.get("/api/v1/cases/case_nope", headers=ANALYST)
    assert missing.status_code == 404 and error_code(missing) == "NOT_FOUND"


async def test_report_scam_adds_the_scam_entities_to_the_watchlist(
    client: httpx.AsyncClient, services: Services
) -> None:
    tan = await run(client, "tan")
    seed_phone = await services.state.get_watchlist("PHONE", "+65 8000 0147")
    assert seed_phone and seed_phone.source == "SEED"
    r = await client.post(
        f"/api/v1/cases/{tan['case_id']}/decision",
        json={"action": "REPORT_SCAM", "note": "Called customer, confirmed MAS impersonation"},
        headers=ANALYST,
    )
    assert r.status_code == 200
    assert r.json() == {"case_id": tan["case_id"], "status": "REPORTED", "watchlist_added": 3}

    domain = await services.state.get_watchlist("DOMAIN", "mas-gov-verify.example")
    assert domain and domain.source == "ANALYST_REPORT" and domain.reported_count == 1
    assert domain.typologies == ["GOV_OFFICIAL_IMPERSONATION"]
    phone = await services.state.get_watchlist("PHONE", "+65 8000 0147")
    assert (
        phone and phone.source == "SEED" and phone.reported_count == seed_phone.reported_count + 1
    )

    case = await services.state.get_case(tan["case_id"])
    assert case and case.status == "REPORTED" and case.decided_at is not None
    assert case.assigned_to == "daniel.lim@harbourbank.example"
    assert case.decision_note == "Called customer, confirmed MAS impersonation"
    audit = await services.state.list_audit(tan["case_id"])
    assert [a.action for a in audit] == ["REPORT_SCAM", "WATCHLIST_ADD"]
    assert audit[1].note and "DOMAIN mas-gov-verify.example" in audit[1].note

    await services.drain()
    (row,) = [x for x in services.analytics.latest_rows(utcnow().replace(year=2000))]
    assert row.analyst_decision == "REPORT_SCAM"


async def test_raj_report_keeps_shared_platforms_and_trusted_contacts_off_the_watchlist(
    client: httpx.AsyncClient, services: Services
) -> None:
    raj = await run(client, "raj")
    r = await client.post(
        f"/api/v1/cases/{raj['case_id']}/decision", json={"action": "REPORT_SCAM"}, headers=ANALYST
    )
    assert r.json()["watchlist_added"] == 3  # phone, payee account, the t.me link itself
    assert await services.state.get_watchlist("DOMAIN", "t.me") is None
    link = await services.state.get_watchlist("URL", "https://t.me/joinchat/gold-slots")
    assert link and link.source == "ANALYST_REPORT"
    assert await services.state.get_watchlist("ACCOUNT", "556-208417-390")


async def test_release_and_unknown_actions(client: httpx.AsyncClient, services: Services) -> None:
    raj = await run(client, "raj")
    r = await client.post(
        f"/api/v1/cases/{raj['case_id']}/decision", json={"action": "RELEASE"}, headers=ANALYST
    )
    assert r.json() == {"case_id": raj["case_id"], "status": "RELEASED", "watchlist_added": 0}
    bad = await client.post(
        f"/api/v1/cases/{raj['case_id']}/decision", json={"action": "DELETE"}, headers=ANALYST
    )
    assert bad.status_code == 422
    nope = await client.post(
        "/api/v1/cases/case_nope/decision", json={"action": "HOLD"}, headers=ANALYST
    )
    assert nope.status_code == 404


# --- metrics ----------------------------------------------------------------------------------


async def test_metrics_from_the_analytics_rows(
    client: httpx.AsyncClient, services: Services
) -> None:
    await run(client, "tan")
    raj = await run(client, "raj")
    await run(client, "aisyah")
    await client.post(
        f"/api/v1/checks/{raj['check_id']}/choice", json={"choice": "COOL_OFF"}, headers=CUSTOMER
    )
    await services.drain()
    old = CheckAnalyticsRow(
        check_id="chk_old", ts=utcnow().replace(year=2020), customer_id="cust_009",
        verdict="RED", amount=99_999, recorded_at=utcnow(),
    )  # fmt: skip
    services.analytics.record([old])

    m = (await client.get("/api/v1/metrics?range=7d", headers=ANALYST)).json()
    assert m["checks"] == 3 and m["verdicts"] == {"GREEN": 1, "AMBER": 1, "RED": 1}
    assert m["money_protected_sgd"] == 8000 + 450  # RED held + AMBER paused
    assert m["false_positive_rate"] == 0.0 and m["latency_ms"]["p50"] >= 0
    assert {t["typology"] for t in m["top_typologies"]} == {
        "GOV_OFFICIAL_IMPERSONATION",
        "JOB_TASK",
    }
    assert m["cost_per_check_usd"] is None  # no prices configured
    today = await client.get("/api/v1/metrics", headers=ANALYST)
    assert today.status_code == 200
    bad = await client.get("/api/v1/metrics?range=1y", headers=ANALYST)
    assert bad.status_code == 422 and error_code(bad) == "VALIDATION_ERROR"


# --- admin, personas, errors, docs ---------------------------------------------------------


async def test_reset_demo(client: httpx.AsyncClient, services: Services) -> None:
    tan = await run(client, "tan")
    await client.post(
        f"/api/v1/cases/{tan['case_id']}/decision", json={"action": "REPORT_SCAM"}, headers=ANALYST
    )
    await services.drain()
    denied = await client.post("/api/v1/admin/reset-demo", headers=ANALYST)
    assert denied.status_code == 403
    r = await client.post("/api/v1/admin/reset-demo", headers=ADMIN)
    assert r.json() == {"checks_deleted": 1, "cases_deleted": 1, "watchlist_deleted": 1}
    assert await services.state.get_check(tan["check_id"]) is None
    assert await services.state.get_watchlist("PHONE", "+65 8000 0147")  # seed entries stay


async def test_personas_are_public(client: httpx.AsyncClient) -> None:
    r = await client.get("/api/v1/personas")
    assert [p["customer_id"] for p in r.json()] == ["cust_001", "cust_002", "cust_003"]


async def test_unexpected_errors_use_the_envelope(
    tmp_path: Path, state: MemoryStateRepo, sqlite_repo: SqliteTransactionRepo
) -> None:
    svc = build_services(tmp_path, state, sqlite_repo)

    async def broken(*_: Any, **__: Any) -> None:
        raise RuntimeError("firestore down with a secret detail")

    svc.state.get_check = broken  # type: ignore[method-assign]
    async with client_for(svc, raise_app_exceptions=False) as c:
        r = await c.get("/api/v1/checks/chk_x", headers=CUSTOMER)
        assert r.status_code == 500 and error_code(r) == "INTERNAL"
        assert "secret" not in r.text
        unknown_route = await c.get("/api/v1/nope")
        assert unknown_route.status_code == 404 and error_code(unknown_route) == "NOT_FOUND"


async def test_openapi_documents_every_route_with_the_error_envelope(
    client: httpx.AsyncClient,
) -> None:
    spec = (await client.get("/openapi.json")).json()
    routes = {(m.upper(), p) for p, ops in spec["paths"].items() for m in ops}
    assert routes == {
        ("POST", "/api/v1/checks"),
        ("POST", "/api/v1/checks/{check_id}/messages"),
        ("GET", "/api/v1/checks/{check_id}"),
        ("GET", "/api/v1/checks/{check_id}/events"),
        ("POST", "/api/v1/checks/{check_id}/choice"),
        ("POST", "/api/v1/checks/{check_id}/feedback"),
        ("POST", "/api/v1/uploads/sign"),
        ("GET", "/api/v1/cases"),
        ("GET", "/api/v1/cases/{case_id}"),
        ("POST", "/api/v1/cases/{case_id}/decision"),
        ("GET", "/api/v1/metrics"),
        ("POST", "/api/v1/admin/reset-demo"),
        ("GET", "/api/v1/personas"),
        ("GET", "/health"),
    }
    for path, ops in spec["paths"].items():
        for op in ops.values():
            assert op.get("summary") and op.get("tags"), path
            for status, resp in op["responses"].items():
                if status.startswith(("4", "5")):
                    ref = resp["content"]["application/json"]["schema"]["$ref"]
                    assert ref.endswith("/ErrorResponse"), (path, status)
    assert (await client.get("/docs")).status_code == 200


def test_transfer_example_matches_the_spec() -> None:
    # API_SPEC's POST /checks example is Mrs Tan's demo transfer.
    assert SCENARIOS["tan"].transfer == Transfer(
        payee_name="Lee Wei Investigation Acct",
        account_number="123-45678-9",
        bank_name="Harbour Bank",
        dest_type="LOCAL_BANK",
        amount=8000,
        note="case 2231",
    )
