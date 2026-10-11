"""checks_analytics rows and the dashboard KPIs (PRD A5), shared by both AnalyticsRepo backends.

    analytics_row(check, case)      the check's whole state as one snapshot row
    compute_metrics(rows, ...)      GET /metrics from the latest snapshot of each check

The KPIs are computed here in Python, not in SQL, so SQLite and BigQuery give identical numbers
and every rule has a unit test. Volumes are dashboard-sized (hundreds of checks a day).
"""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Sequence
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

from app.models.schemas import (
    AnalystAction,
    CaseRecord,
    CaseStatus,
    CheckAnalyticsRow,
    CheckRecord,
    LatencyBin,
    LatencyPercentiles,
    MetricsRange,
    MetricsResponse,
    TypologyCount,
    Verdict,
    VerdictBucket,
)

SGT = ZoneInfo("Asia/Singapore")
TOP_TYPOLOGIES = 5
DECISION_FOR_STATUS: dict[CaseStatus, AnalystAction | None] = {
    "OPEN": None,
    "RELEASED": "RELEASE",
    "HELD": "HOLD",
    "ESCALATED": "ESCALATE",
    "REPORTED": "REPORT_SCAM",
}
# An AMBER check protects the money when the customer does not send it (PRD A5: "AMBER-cancelled").
AMBER_STOPPED = frozenset({"CANCELLED", "COOL_OFF"})
# The dashboard's latency histogram: [0, 2 s), [2 s, 4 s) … [20 s, ∞). The p50/p95 targets are
# 5 s / 10 s (PRD §6), so the bins are finest there.
LATENCY_EDGES_MS = (0, 2000, 4000, 6000, 8000, 10_000, 15_000, 20_000)


def analytics_row(
    check: CheckRecord,
    *,
    model: str,
    case: CaseRecord | None = None,
    recorded_at: datetime | None = None,
) -> CheckAnalyticsRow:
    fusion, evidence = check.fusion, check.evidence
    fast_path = check.status == "DONE" and not check.messages  # GREEN with no check-in
    return CheckAnalyticsRow(
        check_id=check.check_id,
        ts=check.created_at,
        customer_id=check.customer_id,
        amount=check.transfer.amount,
        txn_score=check.txn_risk.score if check.txn_risk else None,
        verdict=fusion.verdict if fusion else None,
        typology=evidence.typology_guess if evidence else None,
        confidence=evidence.typology_confidence if evidence else None,
        latency_ms=check.latency_ms.total,
        tokens_in=check.tokens.in_,
        tokens_out=check.tokens.out,
        model=None if fast_path else model,
        analyst_decision=DECISION_FOR_STATUS[case.status] if case else None,
        customer_choice=check.customer_choice,
        fast_path=fast_path,
        is_eval=check.is_eval,
        recorded_at=recorded_at or datetime.now(UTC),
    )


def range_start(range_: MetricsRange, now: datetime | None = None) -> datetime:
    """`today` starts at 00:00 Singapore time; `7d` is the last 7 × 24 hours."""
    now = now or datetime.now(UTC)
    if range_ == "today":
        midnight = datetime.combine(now.astimezone(SGT).date(), time(0), SGT)
        return midnight.astimezone(UTC)
    return now - timedelta(days=7)


def verdict_buckets(
    rows: Sequence[CheckAnalyticsRow], range_: MetricsRange, now: datetime | None = None
) -> list[VerdictBucket]:
    """Verdict counts over time: hourly since 00:00 Singapore time for `today`, per Singapore
    day for `7d` (every day the 168 hours touch, so 8 buckets). Empty buckets are included, so
    the chart's time axis has no gaps."""
    now = now or datetime.now(UTC)
    hourly = range_ == "today"

    def bucket_of(ts: datetime) -> datetime:
        local = (ts.replace(tzinfo=UTC) if ts.tzinfo is None else ts).astimezone(SGT)
        if hourly:
            return local.replace(minute=0, second=0, microsecond=0)
        return datetime.combine(local.date(), time(0), SGT)

    step = timedelta(hours=1) if hourly else timedelta(days=1)
    buckets: dict[datetime, VerdictBucket] = {}
    t = bucket_of(range_start(range_, now))
    while t <= now:
        buckets[t] = VerdictBucket(start=t)
        t += step
    for r in rows:
        bucket = buckets.get(bucket_of(r.ts))
        if bucket and r.verdict:
            setattr(bucket, r.verdict, getattr(bucket, r.verdict) + 1)
    return list(buckets.values())


def latency_histogram(latencies: Sequence[int]) -> list[LatencyBin]:
    edges = LATENCY_EDGES_MS
    bins = [
        LatencyBin(from_ms=lo, to_ms=edges[i + 1] if i + 1 < len(edges) else None)
        for i, lo in enumerate(edges)
    ]
    for ms in latencies:
        for b in reversed(bins):
            if ms >= b.from_ms:
                b.count += 1
                break
    return bins


def percentile(values: Sequence[int], p: float) -> int:
    """Nearest-rank percentile (0 for no values)."""
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[max(math.ceil(p / 100 * len(ordered)) - 1, 0)]


def compute_metrics(
    rows: Sequence[CheckAnalyticsRow],
    *,
    price_in_per_mtok: float | None = None,
    price_out_per_mtok: float | None = None,
    range_: MetricsRange = "today",
    now: datetime | None = None,
) -> MetricsResponse:
    """`rows` is the latest snapshot of each check (AnalyticsRepo.latest_rows) since
    `range_start(range_, now)`.

    - money protected: RED amounts the analyst did not release, plus AMBER amounts the customer
      did not send (cancelled or paused).
    - false-positive rate: RED checks an analyst released ÷ RED checks (PRD A5).
    - latency: answer -> full customer result, over checks that had a check-in (the GREEN fast
      path has no model call and would flatter the percentiles).
    - cost per check: tokens × the configured price, averaged over every check; null until the
      prices are filled in by hand (never invented).
    """
    verdicts: dict[Verdict, int] = {"GREEN": 0, "AMBER": 0, "RED": 0}
    protected = 0.0
    red = released = 0
    latencies: list[int] = []
    typologies: Counter[str] = Counter()
    for r in rows:
        if r.verdict:
            verdicts[r.verdict] += 1
        amount = r.amount or 0.0
        if r.verdict == "RED":
            red += 1
            if r.analyst_decision == "RELEASE":
                released += 1
            else:
                protected += amount
        elif r.verdict == "AMBER" and r.customer_choice in AMBER_STOPPED:
            protected += amount
        if not r.fast_path and r.latency_ms is not None:
            latencies.append(r.latency_ms)
        if r.verdict in ("AMBER", "RED") and r.typology not in (None, "NONE", "UNKNOWN"):
            typologies[r.typology] += 1

    cost = None
    if rows and price_in_per_mtok is not None and price_out_per_mtok is not None:
        total = sum(
            (r.tokens_in or 0) * price_in_per_mtok + (r.tokens_out or 0) * price_out_per_mtok
            for r in rows
        )
        cost = round(total / 1_000_000 / len(rows), 6)
    top = sorted(typologies.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_TYPOLOGIES]
    return MetricsResponse(
        checks=len(rows),
        verdicts=verdicts,
        money_protected_sgd=round(protected, 2),
        false_positive_rate=round(released / red, 4) if red else 0.0,
        latency_ms=LatencyPercentiles(p50=percentile(latencies, 50), p95=percentile(latencies, 95)),
        top_typologies=[TypologyCount.model_validate({"typology": t, "count": n}) for t, n in top],
        cost_per_check_usd=cost,
        verdicts_over_time=verdict_buckets(rows, range_, now),
        latency_histogram=latency_histogram(latencies),
    )
