"""StateRepo in memory (STATE_BACKEND=memory): unit tests, and `make dev` without the emulator.

It stores the same serialised documents as FirestoreStateRepo (to_doc / to_fields) and
passes the same contract tests (tests/test_state_repo.py), so code tested against it behaves
the same on Firestore. Nothing survives a restart, and nothing is shared between processes.
"""

from __future__ import annotations

import copy
import secrets
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from app.data.base import NotFoundError, as_utc, to_doc, to_fields
from app.data.normalise import normalise_watchlist_value, watchlist_doc_id
from app.models.schemas import (
    AuditEntry,
    CaseRecord,
    CaseStatus,
    ChatMessage,
    CheckRecord,
    FeedbackRecord,
    Persona,
    Typology,
    WatchlistEntry,
    WatchlistSource,
    WatchlistType,
)

Doc = dict[str, Any]


class MemoryStateRepo:
    def __init__(self) -> None:
        self._cols: dict[str, dict[str, Doc]] = {}

    def _col(self, name: str) -> dict[str, Doc]:
        return self._cols.setdefault(name, {})

    def _get(self, name: str, doc_id: str) -> Doc | None:
        doc = self._col(name).get(doc_id)
        return copy.deepcopy(doc) if doc is not None else None

    def _set(self, name: str, doc_id: str, doc: Doc) -> None:
        self._col(name)[doc_id] = copy.deepcopy(doc)

    def _update(self, name: str, doc_id: str, fields: dict[str, Any]) -> None:
        doc = self._col(name).get(doc_id)
        if doc is None:
            raise NotFoundError(f"{name}/{doc_id}")
        doc.update(copy.deepcopy(to_fields(fields)))

    def _sorted(self, name: str, key: str, *, desc: bool) -> list[Doc]:
        docs = [copy.deepcopy(d) for d in self._col(name).values()]
        return sorted(docs, key=lambda d: d[key], reverse=desc)

    def _delete_for_customers(self, name: str, customer_ids: Iterable[str]) -> int:
        ids, col = set(customer_ids), self._col(name)
        doomed = [k for k, d in col.items() if d.get("customer_id") in ids]
        for k in doomed:
            del col[k]
        return len(doomed)

    # --- checks ------------------------------------------------------------------------------

    async def create_check(self, check: CheckRecord) -> None:
        self._set("checks", check.check_id, to_doc(check))

    async def get_check(self, check_id: str) -> CheckRecord | None:
        doc = self._get("checks", check_id)
        return CheckRecord.model_validate(doc) if doc else None

    async def update_check(self, check_id: str, **fields: Any) -> None:
        self._update("checks", check_id, fields)

    async def append_check_message(self, check_id: str, message: ChatMessage) -> None:
        doc = self._col("checks").get(check_id)
        if doc is None:
            raise NotFoundError(f"checks/{check_id}")
        msg = to_doc(message)
        if msg not in doc.setdefault("messages", []):  # ArrayUnion semantics
            doc["messages"].append(msg)

    async def list_checks(
        self, *, customer_id: str | None = None, limit: int = 50
    ) -> list[CheckRecord]:
        docs = self._sorted("checks", "created_at", desc=True)
        if customer_id:
            docs = [d for d in docs if d["customer_id"] == customer_id]
        return [CheckRecord.model_validate(d) for d in docs[:limit]]

    async def delete_checks_for(self, customer_ids: Iterable[str]) -> int:
        return self._delete_for_customers("checks", customer_ids)

    # --- cases -------------------------------------------------------------------------------

    async def create_case(self, case: CaseRecord) -> None:
        self._set("cases", case.case_id, to_doc(case))

    async def get_case(self, case_id: str) -> CaseRecord | None:
        doc = self._get("cases", case_id)
        return CaseRecord.model_validate(doc) if doc else None

    async def update_case(self, case_id: str, **fields: Any) -> None:
        self._update("cases", case_id, fields)

    async def list_cases(
        self, *, status: CaseStatus | None = None, limit: int = 50
    ) -> list[CaseRecord]:
        docs = self._sorted("cases", "created_at", desc=True)
        if status:
            docs = [d for d in docs if d["status"] == status]
        return [CaseRecord.model_validate(d) for d in docs[:limit]]

    async def delete_cases_for(self, customer_ids: Iterable[str]) -> int:
        return self._delete_for_customers("cases", customer_ids)

    # --- audit (append-only) -----------------------------------------------------------------

    async def append_audit(self, entry: AuditEntry) -> str:
        doc_id = secrets.token_hex(10)
        self._set("audit", doc_id, to_doc(entry))
        return doc_id

    async def list_audit(self, case_id: str) -> list[AuditEntry]:
        docs = self._sorted("audit", "ts", desc=False)
        return [AuditEntry.model_validate(d) for d in docs if d["case_id"] == case_id]

    # --- watchlist ---------------------------------------------------------------------------

    async def get_watchlist(self, type_: WatchlistType, value: str) -> WatchlistEntry | None:
        norm = normalise_watchlist_value(type_, value)
        doc = self._get("watchlist", watchlist_doc_id(norm))
        return WatchlistEntry.model_validate(doc) if doc else None

    async def upsert_watchlist(
        self,
        type_: WatchlistType,
        value: str,
        *,
        source: WatchlistSource,
        typologies: Iterable[Typology] = (),
        ts: datetime | None = None,
    ) -> WatchlistEntry:
        norm = normalise_watchlist_value(type_, value)
        doc_id, now, typos = watchlist_doc_id(norm), as_utc(ts), sorted(set(typologies))
        doc = self._col("watchlist").get(doc_id)
        if doc is None:
            entry = WatchlistEntry(
                type=type_,
                value=norm,
                source=source,
                reported_count=1,
                first_seen=now,
                last_seen=now,
                typologies=typos,
            )
            self._set("watchlist", doc_id, to_doc(entry))
            return entry
        doc["reported_count"] += 1
        doc["last_seen"] = now
        doc["typologies"] += [t for t in typos if t not in doc["typologies"]]
        return WatchlistEntry.model_validate(copy.deepcopy(doc))

    async def put_watchlist(self, entry: WatchlistEntry) -> None:
        norm = normalise_watchlist_value(entry.type, entry.value)
        self._set(
            "watchlist", watchlist_doc_id(norm), to_doc(entry.model_copy(update={"value": norm}))
        )

    async def list_watchlist(self, *, limit: int = 500) -> list[WatchlistEntry]:
        docs = self._sorted("watchlist", "last_seen", desc=True)
        return [WatchlistEntry.model_validate(d) for d in docs[:limit]]

    async def delete_watchlist(self, *, source: WatchlistSource) -> int:
        col = self._col("watchlist")
        doomed = [k for k, d in col.items() if d["source"] == source]
        for k in doomed:
            del col[k]
        return len(doomed)

    # --- feedback ----------------------------------------------------------------------------

    async def add_feedback(self, feedback: FeedbackRecord) -> str:
        doc_id = secrets.token_hex(10)
        self._set("feedback", doc_id, to_doc(feedback))
        return doc_id

    # --- personas ----------------------------------------------------------------------------

    async def put_persona(self, persona: Persona) -> None:
        self._set("personas", persona.customer_id, to_doc(persona))

    async def get_persona(self, customer_id: str) -> Persona | None:
        doc = self._get("personas", customer_id)
        return Persona.model_validate(doc) if doc else None

    async def list_personas(self) -> list[Persona]:
        docs = self._sorted("personas", "customer_id", desc=False)
        return [Persona.model_validate(d) for d in docs]
