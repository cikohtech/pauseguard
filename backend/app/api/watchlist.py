"""GET /watchlist: the scam-entity watchlist for the console's Watchlist page (analysts only).

Only analyst actions (REPORT_SCAM) and the seed write to it; agents only read it.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import AnalystDep, ServicesDep
from app.api.errors import error_docs
from app.models.schemas import WatchlistEntry

router = APIRouter(tags=["analyst"])


@router.get(
    "/watchlist",
    response_model=list[WatchlistEntry],
    responses=error_docs(401, 403, 422),
    summary="List watchlist entries",
)
async def list_watchlist(
    services: ServicesDep,
    _: AnalystDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 500,
) -> list[WatchlistEntry]:
    """Most recently seen first. `source` is SEED (the synthetic intel feed) or ANALYST_REPORT
    (added by "Report as scam"); `value` is normalised (E.164 phones, bare accounts, lower-case
    domains)."""
    return await services.state.list_watchlist(limit=limit)
