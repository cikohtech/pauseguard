"""StateRepo on Firestore (native mode): checks, cases, audit, watchlist, feedback, personas.

Collections follow DATA_SPEC §3. Locally it talks to the emulator (FIRESTORE_EMULATOR_HOST,
project `demo-pauseguard`); on Cloud Run it uses the service account. Only the API writes
here; browsers only read, through the realtime listener and the Firestore rules.
"""

from __future__ import annotations

import time
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from google.api_core import exceptions as gexc
from google.cloud import firestore
from google.cloud.firestore import ArrayUnion, FieldFilter, Increment

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

CHECKS = "checks"
CASES = "cases"
AUDIT = "audit"
WATCHLIST = "watchlist"
FEEDBACK = "feedback"
PERSONAS = "personas"
IN_QUERY_MAX = 30  # Firestore's limit for an `in` filter
BATCH_MAX = 500
WATCHLIST_CACHE_SECONDS = 30.0
WATCHLIST_CACHE_MAX = 2000


class FirestoreStateRepo:
    def __init__(
        self,
        client: firestore.AsyncClient | None = None,
        *,
        project: str | None = None,
        watchlist_cache_seconds: float = WATCHLIST_CACHE_SECONDS,
    ) -> None:
        self._db = client or firestore.AsyncClient(project=project)
        # Watchlist lookups (hits and misses) are cached per instance for a few seconds: every
        # check looks up the same demo payees and numbers twice. Any watchlist write through
        # this repo (REPORT_SCAM, reset-demo, seeding) clears it, so this instance never serves
        # a stale entry; another Cloud Run instance may, for at most the TTL. 0 turns it off.
        self._wl_ttl = watchlist_cache_seconds
        self._wl_cache: dict[str, tuple[float, WatchlistEntry | None]] = {}
        self._wl_gen = 0  # bumped by every write; a read that raced a write isn't cached

    @property
    def client(self) -> firestore.AsyncClient:
        return self._db

    async def _update(self, collection: str, doc_id: str, fields: dict[str, Any]) -> None:
        try:
            await self._db.collection(collection).document(doc_id).update(to_fields(fields))
        except gexc.NotFound as e:
            raise NotFoundError(f"{collection}/{doc_id}") from e

    async def _delete_where(self, query: Any) -> int:
        n, batch = 0, self._db.batch()
        async for snap in query.stream():
            batch.delete(snap.reference)
            n += 1
            if n % BATCH_MAX == 0:
                await batch.commit()
                batch = self._db.batch()
        if n % BATCH_MAX:
            await batch.commit()
        return n

    async def _delete_for_customers(self, collection: str, customer_ids: Iterable[str]) -> int:
        ids, n = list(dict.fromkeys(customer_ids)), 0
        for i in range(0, len(ids), IN_QUERY_MAX):
            q = self._db.collection(collection).where(
                filter=FieldFilter("customer_id", "in", ids[i : i + IN_QUERY_MAX])
            )
            n += await self._delete_where(q)
        return n

    # --- checks ------------------------------------------------------------------------------

    async def create_check(self, check: CheckRecord) -> None:
        await self._db.collection(CHECKS).document(check.check_id).set(to_doc(check))

    async def get_check(self, check_id: str) -> CheckRecord | None:
        snap = await self._db.collection(CHECKS).document(check_id).get()
        return CheckRecord.model_validate(snap.to_dict()) if snap.exists else None

    async def update_check(self, check_id: str, **fields: Any) -> None:
        await self._update(CHECKS, check_id, fields)

    async def append_check_message(self, check_id: str, message: ChatMessage) -> None:
        await self._update(CHECKS, check_id, {"messages": ArrayUnion([to_doc(message)])})

    async def list_checks(
        self, *, customer_id: str | None = None, limit: int = 50
    ) -> list[CheckRecord]:
        q: Any = self._db.collection(CHECKS)
        if customer_id:
            q = q.where(filter=FieldFilter("customer_id", "==", customer_id))
        q = q.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
        return [CheckRecord.model_validate(s.to_dict()) async for s in q.stream()]

    async def delete_checks_for(self, customer_ids: Iterable[str]) -> int:
        return await self._delete_for_customers(CHECKS, customer_ids)

    # --- cases -------------------------------------------------------------------------------

    async def create_case(self, case: CaseRecord) -> None:
        await self._db.collection(CASES).document(case.case_id).set(to_doc(case))

    async def get_case(self, case_id: str) -> CaseRecord | None:
        snap = await self._db.collection(CASES).document(case_id).get()
        return CaseRecord.model_validate(snap.to_dict()) if snap.exists else None

    async def update_case(self, case_id: str, **fields: Any) -> None:
        await self._update(CASES, case_id, fields)

    async def list_cases(
        self, *, status: CaseStatus | None = None, limit: int = 50
    ) -> list[CaseRecord]:
        q: Any = self._db.collection(CASES)
        if status:
            q = q.where(filter=FieldFilter("status", "==", status))
        q = q.order_by("created_at", direction=firestore.Query.DESCENDING).limit(limit)
        return [CaseRecord.model_validate(s.to_dict()) async for s in q.stream()]

    async def delete_cases_for(self, customer_ids: Iterable[str]) -> int:
        return await self._delete_for_customers(CASES, customer_ids)

    # --- audit (append-only) -----------------------------------------------------------------

    async def append_audit(self, entry: AuditEntry) -> str:
        _, ref = await self._db.collection(AUDIT).add(to_doc(entry))
        return str(ref.id)

    async def list_audit(self, case_id: str) -> list[AuditEntry]:
        q = (
            self._db.collection(AUDIT)
            .where(filter=FieldFilter("case_id", "==", case_id))
            .order_by("ts")
        )
        return [AuditEntry.model_validate(s.to_dict()) async for s in q.stream()]

    # --- watchlist ---------------------------------------------------------------------------

    def _wl_ref(self, type_: WatchlistType, value: str) -> tuple[Any, str]:
        norm = normalise_watchlist_value(type_, value)
        return self._db.collection(WATCHLIST).document(watchlist_doc_id(norm)), norm

    def _wl_written(self) -> None:
        self._wl_gen += 1
        self._wl_cache.clear()

    async def get_watchlist(self, type_: WatchlistType, value: str) -> WatchlistEntry | None:
        ref, _ = self._wl_ref(type_, value)
        now, gen = time.monotonic(), self._wl_gen
        if (hit := self._wl_cache.get(ref.id)) and hit[0] > now:
            return hit[1]
        snap = await ref.get()
        entry = WatchlistEntry.model_validate(snap.to_dict()) if snap.exists else None
        if self._wl_ttl > 0 and gen == self._wl_gen:
            if len(self._wl_cache) >= WATCHLIST_CACHE_MAX:
                self._wl_cache.clear()
            self._wl_cache[ref.id] = (now + self._wl_ttl, entry)
        return entry

    async def upsert_watchlist(
        self,
        type_: WatchlistType,
        value: str,
        *,
        source: WatchlistSource,
        typologies: Iterable[Typology] = (),
        ts: datetime | None = None,
    ) -> WatchlistEntry:
        ref, norm = self._wl_ref(type_, value)
        now, typos = as_utc(ts), sorted(set(typologies))
        new = WatchlistEntry(
            type=type_,
            value=norm,
            source=source,
            reported_count=1,
            first_seen=now,
            last_seen=now,
            typologies=typos,
        )
        try:
            await ref.create(to_doc(new))  # atomic: fails if the entry exists
        except gexc.Conflict:  # AlreadyExists
            update: dict[str, Any] = {"reported_count": Increment(1), "last_seen": now}
            if typos:
                update["typologies"] = ArrayUnion(typos)
            await ref.update(update)
        self._wl_written()
        snap = await ref.get()
        return WatchlistEntry.model_validate(snap.to_dict())

    async def put_watchlist(self, entry: WatchlistEntry) -> None:
        ref, norm = self._wl_ref(entry.type, entry.value)
        await ref.set(to_doc(entry.model_copy(update={"value": norm})))
        self._wl_written()

    async def list_watchlist(self, *, limit: int = 500) -> list[WatchlistEntry]:
        q = (
            self._db.collection(WATCHLIST)
            .order_by("last_seen", direction=firestore.Query.DESCENDING)
            .limit(limit)
        )
        return [WatchlistEntry.model_validate(s.to_dict()) async for s in q.stream()]

    async def delete_watchlist(self, *, source: WatchlistSource) -> int:
        q = self._db.collection(WATCHLIST).where(filter=FieldFilter("source", "==", source))
        deleted = await self._delete_where(q)
        self._wl_written()
        return deleted

    # --- feedback ----------------------------------------------------------------------------

    async def add_feedback(self, feedback: FeedbackRecord) -> str:
        _, ref = await self._db.collection(FEEDBACK).add(to_doc(feedback))
        return str(ref.id)

    # --- personas ----------------------------------------------------------------------------

    async def put_persona(self, persona: Persona) -> None:
        await self._db.collection(PERSONAS).document(persona.customer_id).set(to_doc(persona))

    async def get_persona(self, customer_id: str) -> Persona | None:
        snap = await self._db.collection(PERSONAS).document(customer_id).get()
        return Persona.model_validate(snap.to_dict()) if snap.exists else None

    async def list_personas(self) -> list[Persona]:
        q = self._db.collection(PERSONAS).order_by("customer_id")
        return [Persona.model_validate(s.to_dict()) async for s in q.stream()]
