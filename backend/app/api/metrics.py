"""GET /metrics: the dashboard KPIs (PRD A5) from checks_analytics (BigQuery in cloud)."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AnalystDep, ServicesDep
from app.api.errors import error_docs
from app.data.analytics import compute_metrics, range_start
from app.models.schemas import MetricsRange, MetricsResponse

router = APIRouter(tags=["analyst"])


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    responses=error_docs(401, 403, 422),
    summary="Dashboard KPIs",
)
async def metrics(
    services: ServicesDep,
    _: AnalystDep,
    range_: Annotated[MetricsRange, Query(alias="range")] = "today",
) -> MetricsResponse:
    """`today` (since 00:00 Singapore time) or `7d`. Money protected = RED amounts not released
    by an analyst + AMBER amounts the customer cancelled or paused. False-positive rate = RED
    checks released ÷ RED checks. Latency = check-in answer → full customer result (p50/p95,
    checks with a check-in only). `cost_per_check_usd` is null until the Gemini prices are set.
    Benchmark traffic is excluded. `verdicts_over_time` is hourly (today) or per Singapore day
    (7d); `latency_histogram` bins the same latencies as the percentiles."""
    s = services.settings
    now = datetime.now(UTC)
    rows = await asyncio.to_thread(services.analytics.latest_rows, range_start(range_, now))
    return compute_metrics(
        rows,
        price_in_per_mtok=s.gemini_price_in_usd_per_mtok,
        price_out_per_mtok=s.gemini_price_out_usd_per_mtok,
        range_=range_,
        now=now,
    )
