"""compute_txn_risk (AGENTS_SPEC §1): every row of the points table, its edges, the cap at 100,
the one-repo-call contract, and the rules-only baseline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from app.data.sqlite_repo import SqliteTransactionRepo
from app.models.schemas import DestType, RiskSnapshot, Transfer, TxnFeatures
from app.tools.txn_features import (
    build_features,
    compute_txn_risk,
    rules_only_verdict,
    score_features,
)
from tests.conftest import AS_OF

SGT = timezone(timedelta(hours=8))
NOON_SGT = datetime(2026, 10, 9, 12, 0, tzinfo=SGT)


def feats(**kw: Any) -> TxnFeatures:
    """A transfer that scores 0 unless a test switches a feature on."""
    base: dict[str, Any] = {
        "is_new_payee": False,
        "amount_vs_median_90d": 1.0,
        "dest_type": "LOCAL_BANK",
        "transfers_to_new_payees_24h": 0,
        "hour_local": 12,
        "customer_age": 35,
        "balance_share": 0.1,
        "watchlist_hit": False,
    }
    return TxnFeatures(**(base | kw))


def codes(f: TxnFeatures, **kw: Any) -> dict[str, int]:
    return {r.code: r.points for r in score_features(f, **kw).reasons}


def test_baseline_scores_zero() -> None:
    risk = score_features(feats())
    assert risk.score == 0 and risk.reasons == []


def test_new_payee() -> None:
    assert codes(feats(is_new_payee=True)) == {"NEW_PAYEE": 20}


@pytest.mark.parametrize(
    ("ratio", "points"),
    [(None, None), (2.99, None), (3.0, 20), (9.99, 20), (10.0, 30), (184.0, 30)],
)
def test_amount_spike(ratio: float | None, points: int | None) -> None:
    got = codes(feats(amount_vs_median_90d=ratio)).get("AMOUNT_SPIKE")
    assert got == points


@pytest.mark.parametrize(
    ("dest", "expected"),
    [
        ("CRYPTO_EXCHANGE", {"CRYPTO_DESTINATION": 25}),
        ("OVERSEAS", {"OVERSEAS_DESTINATION": 15}),
        ("LOCAL_BANK", {}),
        ("PAYNOW", {}),
        ("MERCHANT", {}),
    ],
)
def test_destination(dest: DestType, expected: dict[str, int]) -> None:
    assert codes(feats(dest_type=dest)) == expected


@pytest.mark.parametrize(("count", "fires"), [(0, False), (1, False), (2, True), (5, True)])
def test_new_payee_velocity(count: int, fires: bool) -> None:
    got = codes(feats(transfers_to_new_payees_24h=count))
    assert ("NEW_PAYEE_VELOCITY" in got) is fires
    if fires:
        assert got["NEW_PAYEE_VELOCITY"] == 15


@pytest.mark.parametrize(("hour", "fires"), [(23, False), (0, True), (5, True), (6, False)])
def test_night_time(hour: int, fires: bool) -> None:
    assert codes(feats(hour_local=hour)) == ({"NIGHT_TIME": 5} if fires else {})


@pytest.mark.parametrize(("age", "fires"), [(None, False), (59, False), (60, True), (67, True)])
def test_senior_customer(age: int | None, fires: bool) -> None:
    assert codes(feats(customer_age=age)) == ({"SENIOR_CUSTOMER": 5} if fires else {})


@pytest.mark.parametrize(("share", "fires"), [(None, False), (0.49, False), (0.5, True), (3, True)])
def test_balance_share(share: float | None, fires: bool) -> None:
    assert codes(feats(balance_share=share)) == ({"HIGH_BALANCE_SHARE": 15} if fires else {})


def test_balance_share_with_empty_balance() -> None:
    # No share can be computed, but any amount is at least half of a zero balance.
    assert codes(feats(balance_share=None), balance=0.0) == {"HIGH_BALANCE_SHARE": 15}
    assert codes(feats(balance_share=None), balance=None) == {}


def test_watchlist_match() -> None:
    risk = score_features(feats(watchlist_hit=True))
    assert risk.score == 40
    assert [r.code for r in risk.reasons] == ["WATCHLIST_MATCH"]


def test_cap_at_100() -> None:
    everything = feats(
        is_new_payee=True,
        amount_vs_median_90d=50,
        dest_type="CRYPTO_EXCHANGE",
        transfers_to_new_payees_24h=3,
        hour_local=2,
        customer_age=70,
        balance_share=0.9,
        watchlist_hit=True,
    )
    risk = score_features(everything)
    assert sum(r.points for r in risk.reasons) == 20 + 30 + 25 + 15 + 5 + 5 + 15 + 40
    assert risk.score == 100
    assert risk.features == everything


# --- build_features: snapshot + transfer -> features ---------------------------------------


def snapshot(**kw: Any) -> RiskSnapshot:
    base: dict[str, Any] = {
        "customer_id": "cust_x",
        "customer_age": 40,
        "balance": 10_000.0,
        "payee_known": True,
        "median_debit_90d": 100.0,
        "debit_count_90d": 30,
        "transfers_to_new_payees_24h": 0,
    }
    return RiskSnapshot(**(base | kw))


def transfer(amount: float = 100.0, dest: DestType = "LOCAL_BANK") -> Transfer:
    return Transfer(
        payee_name="A Payee", account_number="111-22222-3", amount=amount, dest_type=dest
    )


def test_build_features_ratios_and_hour() -> None:
    f = build_features(snapshot(), transfer(1_234.0), now=NOON_SGT)
    assert f.amount_vs_median_90d == 12.34
    assert f.balance_share == 0.1234
    assert f.hour_local == 12
    # Local time is Singapore: 18:30 UTC is 02:30 the next morning.
    late = datetime(2026, 10, 9, 18, 30, tzinfo=UTC)
    assert build_features(snapshot(), transfer(), now=late).hour_local == 2


def test_build_features_without_history_or_balance() -> None:
    f = build_features(snapshot(median_debit_90d=None, balance=None), transfer(), now=NOON_SGT)
    assert f.amount_vs_median_90d is None and f.balance_share is None


def test_velocity_counts_the_current_transfer_to_a_new_payee() -> None:
    one_before = snapshot(payee_known=False, transfers_to_new_payees_24h=1)
    assert build_features(one_before, transfer(), now=NOON_SGT).transfers_to_new_payees_24h == 2
    known_payee = snapshot(payee_known=True, transfers_to_new_payees_24h=1)
    assert build_features(known_payee, transfer(), now=NOON_SGT).transfers_to_new_payees_24h == 1


# --- compute_txn_risk on the synthetic bank (one repo call) -------------------------------


class CountingRepo:
    def __init__(self, inner: SqliteTransactionRepo) -> None:
        self.inner = inner
        self.calls: list[str] = []
        self.backend = inner.backend

    def __getattr__(self, name: str) -> Any:
        self.calls.append(name)
        return getattr(self.inner, name)


def test_compute_makes_exactly_one_repo_call(sqlite_repo: SqliteTransactionRepo) -> None:
    repo = CountingRepo(sqlite_repo)
    t = Transfer(payee_name="Lee Wei Investigation Acct", account_number="123-45678-9", amount=8000)
    compute_txn_risk("cust_001", t, repo=repo, as_of=AS_OF)  # type: ignore[arg-type]
    assert repo.calls == ["risk_snapshot"]


def test_mrs_tan_demo_transfer(sqlite_repo: SqliteTransactionRepo) -> None:
    """S$8,000 to a brand-new 'safe account' from a 67-year-old who only pays bills."""
    t = Transfer(payee_name="Lee Wei Investigation Acct", account_number="123-45678-9", amount=8000)
    noon = AS_OF + timedelta(hours=12)
    risk = compute_txn_risk("cust_001", t, repo=sqlite_repo, as_of=noon)
    got = {r.code: r.points for r in risk.reasons}
    assert got == {"NEW_PAYEE": 20, "AMOUNT_SPIKE": 30, "SENIOR_CUSTOMER": 5}
    assert risk.score == 55
    with_watchlist = compute_txn_risk(
        "cust_001", t, repo=sqlite_repo, as_of=noon, watchlist_hit=True
    )
    assert with_watchlist.score == 95
    assert rules_only_verdict(with_watchlist.score) == "RED"


def test_demo_personas_reach_the_check_in(sqlite_repo: SqliteTransactionRepo) -> None:
    """Raj and Aisyah must score >= 30 (no GREEN fast path), or the demo has no check-in."""
    noon = AS_OF + timedelta(hours=12)
    raj = Transfer(payee_name="Ahmad Danial", account_number="556-208417-390", amount=450)
    aisyah = Transfer(payee_name="Wong Kah Wai", account_number="436-905127-318", amount=3200)
    for cid, t in (("cust_002", raj), ("cust_003", aisyah)):
        assert compute_txn_risk(cid, t, repo=sqlite_repo, as_of=noon).score >= 30


def test_known_payee_is_not_new(
    sqlite_repo: SqliteTransactionRepo, csv_rows: dict[str, list[dict[str, str]]]
) -> None:
    # Pay one of Mrs Tan's existing bill payees again.
    payee = next(
        p for p in csv_rows["payees"] if p["customer_id"] == "cust_001" and p["first_paid_at"]
    )
    t = Transfer(payee_name=payee["payee_name"], account_number=payee["account_number"], amount=50)
    risk = compute_txn_risk("cust_001", t, repo=sqlite_repo, as_of=AS_OF)
    assert risk.features is not None and risk.features.is_new_payee is False
    assert "NEW_PAYEE" not in {r.code for r in risk.reasons}


@pytest.mark.parametrize(
    ("score", "verdict"),
    [(0, "GREEN"), (39, "GREEN"), (40, "AMBER"), (69, "AMBER"), (70, "RED"), (100, "RED")],
)
def test_rules_only_verdict(score: int, verdict: str) -> None:
    assert rules_only_verdict(score) == verdict
