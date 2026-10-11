"""Progress events for GET /checks/{id}/events (SSE), in process.

The orchestrator's `on_event` callback publishes here; each SSE connection subscribes and first
gets the events it missed. Events live in memory on the instance that runs the analysis, so the
SSE route also reads the check document while it waits: a client connected to another Cloud Run
instance still gets `done` from Firestore (and the MVP UI may simply poll GET /checks/{id}).
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

from app.models.schemas import ProgressEvent

TERMINAL = frozenset({"done", "error"})
HISTORY_TTL_SECONDS = 120.0  # a late subscriber after this reads the check document instead


class EventHub:
    def __init__(self) -> None:
        self._history: dict[str, list[ProgressEvent]] = {}
        self._subs: dict[str, set[asyncio.Queue[ProgressEvent]]] = {}

    def publish(self, check_id: str, event: ProgressEvent) -> None:
        self._history.setdefault(check_id, []).append(event)
        for q in self._subs.get(check_id, ()):
            q.put_nowait(event)
        if event.type in TERMINAL:
            asyncio.get_running_loop().call_later(
                HISTORY_TTL_SECONDS, self._history.pop, check_id, None
            )

    @contextmanager
    def subscribe(
        self, check_id: str
    ) -> Iterator[tuple[list[ProgressEvent], asyncio.Queue[ProgressEvent]]]:
        """(events so far, queue of the next ones). Both are taken in one synchronous step, so
        no event can fall between them."""
        q: asyncio.Queue[ProgressEvent] = asyncio.Queue()
        self._subs.setdefault(check_id, set()).add(q)
        try:
            yield list(self._history.get(check_id, ())), q
        finally:
            subs = self._subs.get(check_id)
            if subs is not None:
                subs.discard(q)
                if not subs:
                    del self._subs[check_id]
