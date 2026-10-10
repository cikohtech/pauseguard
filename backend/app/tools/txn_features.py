"""Transaction risk (AGENTS_SPEC §1): a points table over a few behavioural features. No LLM.

    compute_txn_risk(customer_id, transfer, repo=...)   one repo call (risk_snapshot), then pure
    risk_from_snapshot(snapshot, transfer, now=...)     the pure part, snapshot fetched elsewhere
    build_features(snapshot, transfer, now=..., ...)    pure: snapshot + transfer -> TxnFeatures
    score_features(features)                            pure: the points table -> TxnRisk
    rules_only_verdict(score)                           benchmark baseline B0 (EVAL_PLAN)

The watchlist lives in Firestore (async), so the caller looks the payee account up and passes
`watchlist_hit`; this keeps the tool synchronous with exactly one TransactionRepo call.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.data.base import TransactionRepo, as_utc
from app.models.schemas import (
    RiskSnapshot,
    Transfer,
    TxnFeatures,
    TxnReasonCode,
    TxnRisk,
    TxnRiskReason,
    Verdict,
)

LOCAL_TZ = ZoneInfo("Asia/Singapore")

# The points table, exactly as AGENTS_SPEC §1.
POINTS: dict[TxnReasonCode, int] = {
    "NEW_PAYEE": 20,
    "AMOUNT_SPIKE": 20,  # >= 3x the 90-day median debit
    "CRYPTO_DESTINATION": 25,
    "OVERSEAS_DESTINATION": 15,
    "NEW_PAYEE_VELOCITY": 15,
    "NIGHT_TIME": 5,
    "SENIOR_CUSTOMER": 5,
    "HIGH_BALANCE_SHARE": 15,
    "WATCHLIST_MATCH": 40,
}
AMOUNT_SPIKE_BIG_POINTS = 30  # >= 10x replaces the 20 points, it doesn't add to them
SPIKE_RATIO = 3.0
BIG_SPIKE_RATIO = 10.0
VELOCITY_MIN = 2
NIGHT_HOURS = range(0, 6)  # 00:00-05:59 local
SENIOR_AGE = 60
BALANCE_SHARE_MIN = 0.5
MAX_SCORE = 100

# Rules-only baseline B0: the transaction score alone.
RULES_RED_MIN = 70
RULES_AMBER_MIN = 40


def build_features(
    snapshot: RiskSnapshot,
    transfer: Transfer,
    *,
    now: datetime,
    watchlist_hit: bool = False,
) -> TxnFeatures:
    """The features for this transfer. `transfers_to_new_payees_24h` counts the current transfer
    too when it goes to a new payee, so ">= 2" means "the second new payee within 24 hours"."""
    is_new_payee = not snapshot.payee_known
    median = snapshot.median_debit_90d
    ratio = round(transfer.amount / median, 2) if median and median > 0 else None
    balance = snapshot.balance
    share = round(transfer.amount / balance, 4) if balance and balance > 0 else None
    return TxnFeatures(
        is_new_payee=is_new_payee,
        amount_vs_median_90d=ratio,
        dest_type=transfer.dest_type,
        transfers_to_new_payees_24h=snapshot.transfers_to_new_payees_24h + int(is_new_payee),
        hour_local=as_utc(now).astimezone(LOCAL_TZ).hour,
        customer_age=snapshot.customer_age,
        balance_share=share,
        watchlist_hit=watchlist_hit,
    )


def _balance_share_hit(f: TxnFeatures, balance: float | None) -> bool:
    if f.balance_share is not None:
        return f.balance_share >= BALANCE_SHARE_MIN
    # A zero or negative balance: any amount is at least half of it.
    return balance is not None and balance <= 0


def score_features(f: TxnFeatures, *, balance: float | None = None) -> TxnRisk:
    """Apply the points table. `balance` only matters when it is zero or negative (no share)."""
    reasons: list[TxnRiskReason] = []

    def add(code: TxnReasonCode, label: str, points: int | None = None) -> None:
        pts = POINTS[code] if points is None else points
        reasons.append(TxnRiskReason(code=code, label=label, points=pts))

    if f.is_new_payee:
        add("NEW_PAYEE", "First transfer to this account")
    if f.amount_vs_median_90d is not None and f.amount_vs_median_90d >= SPIKE_RATIO:
        big = f.amount_vs_median_90d >= BIG_SPIKE_RATIO
        add(
            "AMOUNT_SPIKE",
            f"Amount is {f.amount_vs_median_90d:g}x the usual 90-day payment",
            AMOUNT_SPIKE_BIG_POINTS if big else None,
        )
    if f.dest_type == "CRYPTO_EXCHANGE":
        add("CRYPTO_DESTINATION", "Destination is a crypto exchange")
    elif f.dest_type == "OVERSEAS":
        add("OVERSEAS_DESTINATION", "Destination is an overseas account")
    if f.transfers_to_new_payees_24h >= VELOCITY_MIN:
        add(
            "NEW_PAYEE_VELOCITY",
            f"{f.transfers_to_new_payees_24h} transfers to new payees in 24 hours",
        )
    if f.hour_local in NIGHT_HOURS:
        add("NIGHT_TIME", "Sent between midnight and 6 am")
    if f.customer_age is not None and f.customer_age >= SENIOR_AGE:
        add("SENIOR_CUSTOMER", f"Customer is {f.customer_age}")
    if _balance_share_hit(f, balance):
        pct = f"{f.balance_share:.0%} of the balance" if f.balance_share else "the whole balance"
        add("HIGH_BALANCE_SHARE", f"Amount is {pct}")
    if f.watchlist_hit:
        add("WATCHLIST_MATCH", "Payee account is on the scam watchlist")

    score = min(MAX_SCORE, sum(r.points for r in reasons))
    return TxnRisk(score=score, reasons=reasons, features=f)


def compute_txn_risk(
    customer_id: str,
    transfer: Transfer,
    *,
    repo: TransactionRepo,
    watchlist_hit: bool = False,
    as_of: datetime | None = None,
) -> TxnRisk:
    """Score a transfer before it is sent. One repo call; `as_of` pins "now" for the benchmark."""
    now = as_utc(as_of)
    snapshot = repo.risk_snapshot(customer_id, transfer.account_number, as_of=now)
    return risk_from_snapshot(snapshot, transfer, now=now, watchlist_hit=watchlist_hit)


def risk_from_snapshot(
    snapshot: RiskSnapshot, transfer: Transfer, *, now: datetime, watchlist_hit: bool = False
) -> TxnRisk:
    """The pure half of compute_txn_risk, for callers that fetch the snapshot themselves
    (the orchestrator runs it concurrently with the payee watchlist lookup)."""
    features = build_features(snapshot, transfer, now=now, watchlist_hit=watchlist_hit)
    return score_features(features, balance=snapshot.balance)


def rules_only_verdict(score: int) -> Verdict:
    """Baseline B0 (EVAL_PLAN): RED if score >= 70, AMBER if >= 40, else GREEN."""
    if score >= RULES_RED_MIN:
        return "RED"
    if score >= RULES_AMBER_MIN:
        return "AMBER"
    return "GREEN"
