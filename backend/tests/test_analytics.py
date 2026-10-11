"""checks_analytics: snapshot rows, latest-wins reads (SQLite), and every KPI rule (PRD A5)."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from app.data.analytics import (
    analytics_row,
    compute_metrics,
    latency_histogram,
    percentile,
    range_start,
    verdict_buckets,
)
from app.data.sqlite_repo import SqliteAnalyticsRepo
from app.models.schemas import (
    CaseRecord,
    ChatMessage,
    CheckAnalyticsRow,
    CheckRecord,
    EvidenceAnalysis,
    FusionResult,
    LatencyMs,
    TokenUsage,
    Transfer,
    TxnRisk,
)
from tests.api_support import analytics_db

NOW = datetime(2026, 10, 11, 4, 0, tzinfo=UTC)  # 12:00 in Singapore


def row(check_id: str, **kw: Any) -> CheckAnalyticsRow:
    base: dict[str, Any] = {
        "check_id": check_id,
        "ts": NOW - timedelta(hours=1),
        "customer_id": "cust_001",
        "amount": 100.0,
        "verdict": "GREEN",
        "latency_ms": 4000,
        "tokens_in": 1000,
        "tokens_out": 200,
        "recorded_at": NOW,
    }
    return CheckAnalyticsRow.model_validate(base | kw)


def check(**kw: Any) -> CheckRecord:
    base: dict[str, Any] = {
        "check_id": "chk_1",
        "customer_id": "cust_001",
        "created_at": NOW,
        "status": "DONE",
        "transfer": Transfer(payee_name="X", account_number="1", amount=8000),
        "txn_risk": TxnRisk(score=95),
        "messages": [ChatMessage(role="assistant", text="?", ts=NOW)],
        "evidence": EvidenceAnalysis(
            evidence_present=True,
            summary="s",
            typology_guess="GOV_OFFICIAL_IMPERSONATION",
            typology_confidence=0.99,
        ),
        "fusion": FusionResult(verdict="RED", action="HOLD_FOR_REVIEW"),
        "latency_ms": LatencyMs(txn=40, total=5200),
        "tokens": TokenUsage(in_=2500, out=490),
        "customer_choice": "COOL_OFF",
    }
    return CheckRecord.model_validate(base | kw)


# --- analytics_row -----------------------------------------------------------------------------


def test_row_carries_the_whole_check_state() -> None:
    case = CaseRecord(
        case_id="case_1", check_id="chk_1", customer_id="cust_001", customer_name="Tan",
        amount=8000, verdict="RED", typology="GOV_OFFICIAL_IMPERSONATION", confidence=0.99,
        created_at=NOW, status="REPORTED",
    )  # fmt: skip
    r = analytics_row(check(), model="gemini-x", case=case, recorded_at=NOW)
    assert (r.verdict, r.typology, r.confidence, r.txn_score) == (
        "RED",
        "GOV_OFFICIAL_IMPERSONATION",
        0.99,
        95,
    )
    assert (r.latency_ms, r.tokens_in, r.tokens_out, r.model) == (5200, 2500, 490, "gemini-x")
    assert r.analyst_decision == "REPORT_SCAM" and r.customer_choice == "COOL_OFF"
    assert not r.fast_path and not r.is_eval and r.ts == NOW


def test_fast_path_green_has_no_model_and_open_cases_no_decision() -> None:
    fast = check(messages=[], evidence=None, fusion=FusionResult(verdict="GREEN", action="PROCEED"))
    r = analytics_row(fast, model="gemini-x")
    assert r.fast_path and r.model is None and r.typology is None
    open_case = CaseRecord(
        case_id="c", check_id="chk_1", customer_id="cust_001", customer_name="T", amount=1,
        verdict="AMBER", typology="UNKNOWN", confidence=0, created_at=NOW,
    )  # fmt: skip
    assert analytics_row(check(is_eval=True), model="m", case=open_case).analyst_decision is None
    assert analytics_row(check(is_eval=True), model="m").is_eval


# --- KPIs --------------------------------------------------------------------------------------


def test_money_protected_and_false_positive_rate() -> None:
    rows = [
        row("a", verdict="RED", amount=8000),  # held: protected
        row("b", verdict="RED", amount=5000, analyst_decision="RELEASE"),  # a false positive
        row("c", verdict="RED", amount=700, analyst_decision="REPORT_SCAM"),
        row("d", verdict="AMBER", amount=450, customer_choice="COOL_OFF"),
        row("e", verdict="AMBER", amount=300, customer_choice="CANCELLED"),
        row("f", verdict="AMBER", amount=999, customer_choice="PROCEEDED"),  # sent anyway
        row("g", verdict="AMBER", amount=111),  # no choice yet
        row("h", verdict="GREEN", amount=3200, customer_choice="PROCEEDED"),
    ]
    m = compute_metrics(rows)
    assert m.checks == 8 and m.verdicts == {"GREEN": 1, "AMBER": 4, "RED": 3}
    assert m.money_protected_sgd == 8000 + 700 + 450 + 300
    assert m.false_positive_rate == pytest.approx(1 / 3, abs=1e-4)


def test_latency_skips_the_fast_path_and_cost_needs_both_prices() -> None:
    rows = [row(str(i), latency_ms=v) for i, v in enumerate([3000, 4000, 5000, 9000])]
    rows.append(row("fast", latency_ms=40, fast_path=True, tokens_in=0, tokens_out=0))
    rows.append(row("none", latency_ms=None))
    m = compute_metrics(rows)
    assert (m.latency_ms.p50, m.latency_ms.p95) == (4000, 9000)
    assert m.cost_per_check_usd is None
    assert compute_metrics(rows, price_in_per_mtok=0.5).cost_per_check_usd is None
    priced = compute_metrics(rows, price_in_per_mtok=0.5, price_out_per_mtok=2.0)
    # 5 rows × (1000 × 0.5 + 200 × 2.0) / 1e6, averaged over all 6 checks.
    assert priced.cost_per_check_usd == pytest.approx(5 * 900 / 1e6 / 6, abs=1e-6)


def test_top_typologies_count_flagged_checks_only() -> None:
    rows = [
        row("1", verdict="RED", typology="JOB_TASK"),
        row("2", verdict="AMBER", typology="JOB_TASK"),
        row("3", verdict="RED", typology="INVESTMENT"),
        row("4", verdict="GREEN", typology="NONE"),
        row("5", verdict="AMBER", typology="UNKNOWN"),
        row("6", verdict="GREEN", typology="PHISHING"),  # a GREEN is not a flagged check
    ]
    top = compute_metrics(rows).top_typologies
    assert [(t.typology, t.count) for t in top] == [("JOB_TASK", 2), ("INVESTMENT", 1)]


def test_empty_metrics_are_zero() -> None:
    m = compute_metrics([], price_in_per_mtok=1, price_out_per_mtok=1)
    assert m.checks == 0 and m.false_positive_rate == 0 and m.latency_ms.p50 == 0
    assert m.cost_per_check_usd is None and m.verdicts == {"GREEN": 0, "AMBER": 0, "RED": 0}


def test_percentile_is_nearest_rank() -> None:
    assert percentile([], 50) == 0
    assert percentile([7], 95) == 7
    assert percentile(list(range(1, 101)), 50) == 50
    assert percentile(list(range(1, 101)), 95) == 95


def test_verdicts_over_time_are_hourly_today_and_daily_for_7d() -> None:
    rows = [
        row("a", ts=datetime(2026, 10, 11, 0, 30, tzinfo=UTC)),  # 08:30 SGT
        row("b", ts=datetime(2026, 10, 11, 0, 45, tzinfo=UTC), verdict="RED"),
        row("c", ts=datetime(2026, 10, 11, 3, 59), verdict="AMBER"),  # naive = UTC: 11:59 SGT
        row("d", ts=datetime(2026, 10, 10, 15, 0, tzinfo=UTC), verdict=None),  # 23:00 SGT
    ]
    today = verdict_buckets(rows, "today", NOW)
    assert len(today) == 13  # 00:00 … 12:00 Singapore time, empty hours included
    assert today[0].start.isoformat() == "2026-10-11T00:00:00+08:00"
    assert (today[8].GREEN, today[8].RED) == (1, 1) and today[11].AMBER == 1
    assert sum(b.GREEN + b.AMBER + b.RED for b in today) == 3
    week = verdict_buckets(rows, "7d", NOW)
    assert [b.start.day for b in week] == [4, 5, 6, 7, 8, 9, 10, 11]
    assert (week[-1].GREEN, week[-1].AMBER, week[-1].RED) == (1, 1, 1)
    assert compute_metrics(rows, range_="today", now=NOW).verdicts_over_time == today


def test_latency_histogram_bins_are_half_open() -> None:
    bins = latency_histogram([0, 1999, 2000, 5999, 6000, 19_999, 20_000, 90_000])
    assert [(b.from_ms, b.to_ms) for b in bins][:2] == [(0, 2000), (2000, 4000)]
    assert bins[-1].to_ms is None
    assert [b.count for b in bins] == [2, 1, 1, 1, 0, 0, 1, 2]
    rows = [row("fast", fast_path=True, latency_ms=10), row("slow", latency_ms=7000)]
    assert [b.count for b in compute_metrics(rows).latency_histogram] == [0, 0, 0, 1, 0, 0, 0, 0]


def test_today_starts_at_midnight_singapore_time() -> None:
    assert range_start("today", NOW) == datetime(2026, 10, 10, 16, 0, tzinfo=UTC)
    late = datetime(2026, 10, 11, 17, 30, tzinfo=UTC)  # already 12 Oct in Singapore
    assert range_start("today", late) == datetime(2026, 10, 11, 16, 0, tzinfo=UTC)
    assert range_start("7d", NOW) == NOW - timedelta(days=7)


# --- SqliteAnalyticsRepo ------------------------------------------------------------------------


def test_latest_snapshot_per_check_wins(tmp_path: Path) -> None:
    repo = analytics_db(tmp_path / "a.db")
    t = NOW
    repo.record([row("a", verdict="RED", recorded_at=t)])
    repo.record([row("b", recorded_at=t)])
    # Two snapshots within the same second: the microseconds decide.
    repo.record(
        [
            row(
                "a",
                verdict="RED",
                analyst_decision="HOLD",
                recorded_at=t + timedelta(microseconds=5),
            )
        ]
    )
    repo.record(
        [row("a", verdict="RED", analyst_decision="RELEASE", recorded_at=t + timedelta(seconds=9))]
    )
    got = {r.check_id: r for r in repo.latest_rows(NOW - timedelta(days=1))}
    assert set(got) == {"a", "b"} and got["a"].analyst_decision == "RELEASE"
    assert got["a"].ts == NOW - timedelta(hours=1) and got["a"].fast_path is False


def test_since_and_eval_filters(tmp_path: Path) -> None:
    repo = analytics_db(tmp_path / "a.db")
    repo.record(
        [
            row("old", ts=NOW - timedelta(days=9)),
            row("eval", is_eval=True),
            row("live", fast_path=True),
        ]
    )
    since = NOW - timedelta(days=7)
    assert [r.check_id for r in repo.latest_rows(since)] == ["live"]
    assert {r.check_id for r in repo.latest_rows(since, include_eval=True)} == {"eval", "live"}
    assert repo.latest_rows(since)[0].fast_path is True


def test_a_pre_phase_05_table_is_rebuilt(tmp_path: Path) -> None:
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE checks_analytics (check_id TEXT PRIMARY KEY, ts TEXT NOT NULL)")
    conn.execute("CREATE TABLE customers (customer_id TEXT PRIMARY KEY)")
    conn.execute("INSERT INTO customers VALUES ('cust_001')")
    conn.commit()
    conn.close()
    repo = SqliteAnalyticsRepo(db)
    repo.record([row("a"), row("a", recorded_at=NOW + timedelta(seconds=1))])
    assert len(repo.latest_rows(NOW - timedelta(days=1))) == 1
    with sqlite3.connect(db) as c:  # the bank tables are untouched
        assert c.execute("SELECT COUNT(*) FROM customers").fetchone() == (1,)


def test_missing_database_is_an_error_not_a_new_file(tmp_path: Path) -> None:
    repo = SqliteAnalyticsRepo(tmp_path / "nope.db")
    with pytest.raises(FileNotFoundError, match="make seed-local"):
        repo.record([row("a")])
    assert not (tmp_path / "nope.db").exists()
