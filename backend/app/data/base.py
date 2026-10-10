"""Repository interfaces (ARCHITECTURE D6).

`TransactionRepo` reads bank data: SQLite locally, BigQuery in cloud, chosen by DATA_BACKEND.
`StateRepo` holds app state (checks, cases, audit, watchlist, feedback, personas): Firestore
(emulator locally), or an in-memory twin for unit tests.

Shared semantics, so both TransactionRepo backends return identical results:
- Every time window is half-open, [as_of - window, as_of). `as_of` defaults to now (UTC); the
  benchmark pins it so runs are reproducible.
- Account numbers are compared in normalised form (`normalise_account`).
- A payee is "known" if it exists for the customer and was first paid before `as_of`.
- The 90-day median covers every DEBIT in the window (the exact median, as statistics.median).
- A "transfer to a new payee" in the last N hours is a DEBIT in that window to a payee whose
  first payment also falls in that window.
- Ground-truth labels (is_scam_label, scam_typology_label) are never returned.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel

from app.models.schemas import (
    AuditEntry,
    BankTransaction,
    CaseRecord,
    CaseStatus,
    ChatMessage,
    CheckRecord,
    Customer,
    FeedbackRecord,
    Payee,
    Persona,
    RiskSnapshot,
    Typology,
    WatchlistEntry,
    WatchlistSource,
    WatchlistType,
)

HISTORY_DAYS = 90
VELOCITY_HOURS = 24


class NotFoundError(LookupError):
    """An update targeted a document that does not exist (same error from every StateRepo)."""


def to_doc(model: BaseModel) -> dict[str, Any]:
    """A Pydantic model as a Firestore document: datetimes stay datetimes, aliases are used
    (TokenUsage stores `in`), nested models become maps."""
    return model.model_dump(mode="python", by_alias=True)


def to_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Top-level fields for a partial update; model values are serialised like to_doc."""

    def dump(v: Any) -> Any:
        if isinstance(v, BaseModel):
            return to_doc(v)
        if isinstance(v, list | tuple):
            return [dump(x) for x in v]
        if isinstance(v, dict):
            return {k: dump(x) for k, x in v.items()}
        return v

    return {k: dump(v) for k, v in fields.items()}


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(dt: datetime | None) -> datetime:
    """`None` -> now. Naive datetimes are taken to be UTC. Truncated to whole seconds (the
    stored precision), so both backends draw window edges at exactly the same instant."""
    if dt is None:
        dt = utcnow()
    dt = dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
    return dt.replace(microsecond=0)


def window_start(as_of: datetime, *, days: int = 0, hours: int = 0) -> datetime:
    return as_of - timedelta(days=days, hours=hours)


@runtime_checkable
class TransactionRepo(Protocol):
    backend: str

    def get_customer(self, customer_id: str) -> Customer | None: ...

    def get_payee_by_account(self, customer_id: str, account_number: str) -> Payee | None: ...

    def customer_history(
        self, customer_id: str, days: int = HISTORY_DAYS, *, as_of: datetime | None = None
    ) -> list[BankTransaction]:
        """Debits and credits in the window, oldest first."""
        ...

    def recent_new_payee_transfers(
        self, customer_id: str, hours: int = VELOCITY_HOURS, *, as_of: datetime | None = None
    ) -> list[BankTransaction]:
        """Transfers in the window to payees first paid in that same window, oldest first."""
        ...

    def balance(self, customer_id: str) -> float | None: ...

    def risk_snapshot(
        self, customer_id: str, account_number: str, *, as_of: datetime | None = None
    ) -> RiskSnapshot:
        """Every input of compute_txn_risk in ONE query (a single BigQuery round trip)."""
        ...

    def ping(self) -> bool: ...


@runtime_checkable
class StateRepo(Protocol):
    """App state. Async, because it sits on every API request and inside ADK tools.

    `update_*` raise NotFoundError for a missing document. Watchlist methods take the raw
    value and normalise it (normalise.py); the stored `value` is the normalised form.
    `upsert_watchlist` creates an entry with reported_count 1, or increments the count,
    bumps last_seen and adds typologies; an existing entry keeps its source, so the demo
    reset (delete source=ANALYST_REPORT) never removes a seed entry.
    """

    # checks/{check_id}
    async def create_check(self, check: CheckRecord) -> None: ...
    async def get_check(self, check_id: str) -> CheckRecord | None: ...
    async def update_check(self, check_id: str, **fields: Any) -> None: ...
    async def append_check_message(self, check_id: str, message: ChatMessage) -> None: ...
    async def list_checks(
        self, *, customer_id: str | None = None, limit: int = 50
    ) -> list[CheckRecord]: ...
    async def delete_checks_for(self, customer_ids: Iterable[str]) -> int: ...

    # cases/{case_id}
    async def create_case(self, case: CaseRecord) -> None: ...
    async def get_case(self, case_id: str) -> CaseRecord | None: ...
    async def update_case(self, case_id: str, **fields: Any) -> None: ...
    async def list_cases(
        self, *, status: CaseStatus | None = None, limit: int = 50
    ) -> list[CaseRecord]: ...
    async def delete_cases_for(self, customer_ids: Iterable[str]) -> int: ...

    # audit/{auto_id}: append-only
    async def append_audit(self, entry: AuditEntry) -> str: ...
    async def list_audit(self, case_id: str) -> list[AuditEntry]: ...

    # watchlist/{normalised_value}
    async def get_watchlist(self, type_: WatchlistType, value: str) -> WatchlistEntry | None: ...
    async def upsert_watchlist(
        self,
        type_: WatchlistType,
        value: str,
        *,
        source: WatchlistSource,
        typologies: Iterable[Typology] = (),
        ts: datetime | None = None,
    ) -> WatchlistEntry: ...
    async def put_watchlist(self, entry: WatchlistEntry) -> None: ...
    async def list_watchlist(self, *, limit: int = 500) -> list[WatchlistEntry]: ...
    async def delete_watchlist(self, *, source: WatchlistSource) -> int: ...

    # feedback/{auto_id}
    async def add_feedback(self, feedback: FeedbackRecord) -> str: ...

    # personas/{customer_id}
    async def put_persona(self, persona: Persona) -> None: ...
    async def get_persona(self, customer_id: str) -> Persona | None: ...
    async def list_personas(self) -> list[Persona]: ...
