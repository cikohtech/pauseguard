"""StateRepo contract: every test runs on the in-memory repo, and on the Firestore emulator
when one is reachable (`make emulators`). The emulator side uses its own project ID
(demo-pauseguard-test) and wipes it before each test, so dev data is never touched."""

from __future__ import annotations

import asyncio
import os
import urllib.request
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest

from app.data.base import NotFoundError, StateRepo
from app.data.memory_repo import MemoryStateRepo
from app.data.seed import emulator_up
from app.models.schemas import (
    AuditEntry,
    CaseFile,
    CaseRecord,
    ChatMessage,
    CheckRecord,
    EvidenceAnalysis,
    FeedbackRecord,
    Persona,
    RedFlag,
    TokenUsage,
    Transfer,
    TxnRisk,
    WatchlistEntry,
)

EMULATOR = os.environ.get("FIRESTORE_EMULATOR_HOST", "127.0.0.1:8080")
TEST_PROJECT = "demo-pauseguard-test"
T0 = datetime(2026, 10, 12, 9, 30, tzinfo=UTC)


@pytest.fixture(params=["memory", "firestore"])
def repo(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[StateRepo]:
    if request.param == "memory":
        yield MemoryStateRepo()
        return
    if not emulator_up(EMULATOR):
        pytest.skip(f"Firestore emulator not running at {EMULATOR} (make emulators)")
    from app.data.firestore_repo import FirestoreStateRepo

    monkeypatch.setenv("FIRESTORE_EMULATOR_HOST", EMULATOR)
    url = f"http://{EMULATOR}/emulator/v1/projects/{TEST_PROJECT}/databases/(default)/documents"
    urllib.request.urlopen(urllib.request.Request(url, method="DELETE"), timeout=5).close()
    yield FirestoreStateRepo(project=TEST_PROJECT)


def a_check(
    check_id: str = "chk_1", customer_id: str = "cust_001", minutes: int = 0
) -> CheckRecord:
    return CheckRecord(
        check_id=check_id,
        customer_id=customer_id,
        created_at=T0 + timedelta(minutes=minutes),
        status="CHECKIN",
        language="zh",
        transfer=Transfer(
            payee_name="Lee Wei Investigation Acct",
            account_number="123-45678-9",
            bank_name="Harbour Bank",
            amount=8000,
        ),
        txn_risk=TxnRisk(score=95),
        tokens=TokenUsage.model_validate({"in": 1200, "out": 300}),
    )


def a_case(
    case_id: str = "case_1", customer_id: str = "cust_001", minutes: int = 0, status: str = "OPEN"
) -> CaseRecord:
    return CaseRecord.model_validate(
        {
            "case_id": case_id,
            "check_id": "chk_1",
            "customer_id": customer_id,
            "customer_name": "Tan Mei Ling",
            "customer_age": 67,
            "amount": 8000,
            "verdict": "RED",
            "typology": "GOV_OFFICIAL_IMPERSONATION",
            "confidence": 0.93,
            "status": status,
            "created_at": T0 + timedelta(minutes=minutes),
        }
    )


async def test_check_round_trip_and_partial_updates(repo: StateRepo) -> None:
    check = a_check()
    await repo.create_check(check)
    assert await repo.get_check("chk_1") == check
    assert await repo.get_check("chk_missing") is None

    evidence = EvidenceAnalysis(
        evidence_present=True,
        summary="Chat from a self-styled MAS officer.",
        red_flags=[
            RedFlag(
                code="SAFE_ACCOUNT",
                severity="HIGH",
                quote="safe account",
                evidence_index=0,
                box_2d=[410, 60, 470, 940],
            )
        ],
        typology_guess="GOV_OFFICIAL_IMPERSONATION",
        typology_confidence=0.9,
    )
    await repo.update_check("chk_1", status="ANALYSING", evidence=evidence)
    got = await repo.get_check("chk_1")
    assert got is not None
    assert got.status == "ANALYSING" and got.evidence == evidence
    assert got.transfer == check.transfer and got.tokens.in_ == 1200  # untouched fields stay

    with pytest.raises(NotFoundError):
        await repo.update_check("chk_missing", status="DONE")


async def test_messages_are_appended_in_order(repo: StateRepo) -> None:
    await repo.create_check(a_check())
    first = ChatMessage(role="assistant", text="谁让您付这笔钱？", ts=T0)
    second = ChatMessage(
        role="customer",
        text="A government officer",
        evidence_uris=["gs://b/x.png"],
        ts=T0 + timedelta(seconds=20),
    )
    await repo.append_check_message("chk_1", first)
    await repo.append_check_message("chk_1", second)
    got = await repo.get_check("chk_1")
    assert got is not None and got.messages == [first, second]
    with pytest.raises(NotFoundError):
        await repo.append_check_message("chk_missing", first)


async def test_list_and_delete_checks(repo: StateRepo) -> None:
    for i, cid in enumerate(["cust_001", "cust_002", "cust_001", "cust_123"]):
        await repo.create_check(a_check(f"chk_{i}", cid, minutes=i))
    assert [c.check_id for c in await repo.list_checks()] == ["chk_3", "chk_2", "chk_1", "chk_0"]
    assert [c.check_id for c in await repo.list_checks(customer_id="cust_001")] == [
        "chk_2",
        "chk_0",
    ]
    assert len(await repo.list_checks(limit=2)) == 2
    assert await repo.delete_checks_for(["cust_001", "cust_002", "cust_003"]) == 3
    assert [c.check_id for c in await repo.list_checks()] == ["chk_3"]


async def test_cases(repo: StateRepo) -> None:
    await repo.create_case(a_case("case_1", minutes=0))
    await repo.create_case(a_case("case_2", "cust_002", minutes=5))
    await repo.create_case(a_case("case_3", "cust_123", minutes=9, status="HELD"))
    assert [c.case_id for c in await repo.list_cases()] == ["case_3", "case_2", "case_1"]
    assert [c.case_id for c in await repo.list_cases(status="OPEN")] == ["case_2", "case_1"]

    case_file = CaseFile(
        title="MAS impersonation, S$8,000",
        summary="...",
        recommended_action="HOLD",
        recommended_reason="...",
        confidence=0.9,
    )
    await repo.update_case("case_1", status="REPORTED", decided_at=T0, case_file=case_file)
    got = await repo.get_case("case_1")
    assert got is not None and got.status == "REPORTED" and got.case_file == case_file
    assert await repo.get_case("case_missing") is None
    with pytest.raises(NotFoundError):
        await repo.update_case("case_missing", status="HELD")

    assert await repo.delete_cases_for(["cust_001", "cust_002"]) == 2
    assert [c.case_id for c in await repo.list_cases()] == ["case_3"]


async def test_audit_is_listed_per_case_in_time_order(repo: StateRepo) -> None:
    later = AuditEntry(
        actor="daniel", action="REPORT_SCAM", case_id="case_1", ts=T0 + timedelta(minutes=2)
    )
    earlier = AuditEntry(
        actor="daniel", action="HOLD", case_id="case_1", ts=T0, note="Calling her son"
    )
    other = AuditEntry(actor="daniel", action="RELEASE", case_id="case_2", ts=T0)
    ids = [await repo.append_audit(e) for e in (later, earlier, other)]
    assert len(set(ids)) == 3
    assert await repo.list_audit("case_1") == [earlier, later]


async def test_firestore_watchlist_cache(repo: StateRepo) -> None:
    """Lookups are cached per instance (hits and misses); this instance's writes clear the
    cache at once, another instance's writes show up when the TTL runs out."""
    from app.data.firestore_repo import FirestoreStateRepo

    if not isinstance(repo, FirestoreStateRepo):
        pytest.skip("the cache is the Firestore repo's")

    fast = FirestoreStateRepo(project=TEST_PROJECT, watchlist_cache_seconds=0.3)
    other = FirestoreStateRepo(project=TEST_PROJECT)  # another Cloud Run instance
    entry = WatchlistEntry(
        type="PHONE", value="+6580000147", source="SEED", reported_count=6,
        first_seen=T0, last_seen=T0, typologies=[],
    )  # fmt: skip

    assert await fast.get_watchlist("PHONE", "+65 8000 0147") is None  # miss, cached
    await other.put_watchlist(entry)
    assert await fast.get_watchlist("PHONE", "+65 8000 0147") is None  # still the cached miss
    await asyncio.sleep(0.35)
    hit = await fast.get_watchlist("PHONE", "+65 8000 0147")
    assert hit is not None and hit.reported_count == 6  # TTL over: read again

    await fast.upsert_watchlist("PHONE", "+65 8000 0147", source="ANALYST_REPORT")
    bumped = await fast.get_watchlist("PHONE", "+65 8000 0147")
    assert bumped is not None and bumped.reported_count == 7  # own write: fresh at once

    off = FirestoreStateRepo(project=TEST_PROJECT, watchlist_cache_seconds=0)
    await off.get_watchlist("DOMAIN", "x.example")
    assert off._wl_cache == {}


async def test_watchlist_seed_lookup_and_upsert(repo: StateRepo) -> None:
    seed = WatchlistEntry(
        type="PHONE",
        value="+65 8000 0147",
        source="SEED",
        reported_count=6,
        first_seen=T0 - timedelta(days=60),
        last_seen=T0 - timedelta(days=8),
        typologies=["GOV_OFFICIAL_IMPERSONATION"],
    )
    await repo.put_watchlist(seed)
    for variant in ("+65 8000 0147", "80000147", "+6580000147"):
        hit = await repo.get_watchlist("PHONE", variant)
        assert hit is not None and hit.value == "+6580000147" and hit.reported_count == 6
    assert await repo.get_watchlist("PHONE", "+65 8000 0999") is None

    # Re-reporting a seed entry bumps it but keeps it a seed entry.
    bumped = await repo.upsert_watchlist(
        "PHONE",
        "8000 0147",
        source="ANALYST_REPORT",
        typologies=["GOV_OFFICIAL_IMPERSONATION", "PHISHING"],
        ts=T0,
    )
    assert (bumped.reported_count, bumped.source, bumped.last_seen) == (7, "SEED", T0)
    assert bumped.first_seen == seed.first_seen
    assert sorted(bumped.typologies) == ["GOV_OFFICIAL_IMPERSONATION", "PHISHING"]

    new = await repo.upsert_watchlist(
        "URL",
        "https://mas-gov-verify.example/case/2231?id=7",
        source="ANALYST_REPORT",
        typologies=["GOV_OFFICIAL_IMPERSONATION"],
        ts=T0 + timedelta(minutes=1),
    )
    assert (new.value, new.reported_count, new.source) == (
        "mas-gov-verify.example/case/2231",
        1,
        "ANALYST_REPORT",
    )
    again = await repo.upsert_watchlist(
        "URL", "mas-gov-verify.example/case/2231", source="ANALYST_REPORT"
    )
    assert again.reported_count == 2 and again.typologies == ["GOV_OFFICIAL_IMPERSONATION"]
    # A URL without a path is the domain: one entry.
    await repo.upsert_watchlist("DOMAIN", "mas-gov-verify.example", source="ANALYST_REPORT", ts=T0)
    hit = await repo.get_watchlist("URL", "https://www.mas-gov-verify.example/")
    assert hit is not None and hit.type == "DOMAIN"

    listed = await repo.list_watchlist()
    assert len(listed) == 3
    assert [e.last_seen for e in listed] == sorted((e.last_seen for e in listed), reverse=True)
    assert await repo.delete_watchlist(source="ANALYST_REPORT") == 2  # the demo reset
    assert [e.value for e in await repo.list_watchlist()] == ["+6580000147"]


async def test_feedback_and_personas(repo: StateRepo) -> None:
    fb_id = await repo.add_feedback(FeedbackRecord(check_id="chk_1", helpful=True, ts=T0))
    assert fb_id
    for cid, name in (("cust_002", "Raj Kumar"), ("cust_001", "Tan Mei Ling")):
        await repo.put_persona(
            Persona(
                customer_id=cid,
                full_name=name,
                age=60,
                preferred_language="en",
                segment="WORKER",
                story="...",
            )
        )
    assert [p.customer_id for p in await repo.list_personas()] == ["cust_001", "cust_002"]
    got = await repo.get_persona("cust_002")
    assert got is not None and got.full_name == "Raj Kumar"
    assert await repo.get_persona("cust_999") is None
