"""Watchlist lookup (AGENTS_SPEC §3): phones, URLs, domains and accounts against Firestore.

    entities_from_text(text)            regex pass over free text (customer answer, pasted chat)
    lookup_entities(state, ...)         normalised lookups, run concurrently -> [WatchlistMatch]
    watchlist_lookup(...)               the same, as an ADK function tool for the Scam-Intel agent

A URL is checked as a URL and as its domain, so `https://police-sg-case.example/case/7` matches
the DOMAIN entry. The orchestrator calls `lookup_entities` itself (payee account at check start,
then every entity the evidence agent found), so a watchlist hit never depends on an LLM choosing
to call a tool. The tool reads the StateRepo from a context variable (`use_state`) and reports
its matches through `collecting()`.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.data.base import StateRepo
from app.data.normalise import normalise_domain, normalise_watchlist_value
from app.models.schemas import Entities, WatchlistMatch, WatchlistType

# Singapore numbers (+65 8000 0147, 8000 0147) and international ones written with a "+".
_PHONE = re.compile(r"(?<![\w+])(?:\+65[\s-]?)?[3689]\d{3}[\s-]?\d{4}(?!\d)|\+\d[\d\s-]{7,15}\d")
# Bank accounts as banks print them: 123-45678-9, 556-208417-390. Dashes only, so phones
# written with spaces never look like accounts.
_ACCOUNT = re.compile(r"(?<![\w-])\d{3}-\d{4,7}-\d{1,4}(?![\w-])")
_URL = re.compile(r"\bhttps?://[^\s<>\"'()\[\]，。]+", re.I)
_TLDS = r"(?:com|net|org|sg|my|io|co|app|xyz|top|vip|cc|me|info|biz|site|online|link|example)"
_DOMAIN = re.compile(
    rf"(?<![\w@./-])(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+{_TLDS}(?:/[^\s<>\"'()\[\]，。]*)?(?![\w-])",
    re.I,
)

_STATE: ContextVar[StateRepo | None] = ContextVar("watchlist_state", default=None)
_FOUND: ContextVar[list[WatchlistMatch] | None] = ContextVar("watchlist_found", default=None)


def entities_from_text(*texts: str | None) -> Entities:
    """Phones, URLs and accounts found by regex (the quick pass before the evidence agent)."""
    phones: list[str] = []
    urls: list[str] = []
    accounts: list[str] = []
    for text in texts:
        if not text:
            continue
        found_urls = [u.rstrip(".,;:!?)") for u in _URL.findall(text)]
        rest = _URL.sub(" ", text)
        found_urls += [d.rstrip(".,;:!?)") for d in _DOMAIN.findall(rest)]
        urls += found_urls
        rest = _DOMAIN.sub(" ", rest)
        accounts += _ACCOUNT.findall(rest)
        phones += [p.strip() for p in _PHONE.findall(_ACCOUNT.sub(" ", rest))]
    return Entities(phones=_unique(phones), urls=_unique(urls), accounts=_unique(accounts))


def merge_entities(*groups: Entities | None) -> Entities:
    merged = Entities()
    for g in groups:
        if g is None:
            continue
        merged.phones += g.phones
        merged.urls += g.urls
        merged.accounts += g.accounts
        merged.orgs += g.orgs
        merged.apps += g.apps
    return Entities(
        phones=_unique(merged.phones),
        urls=_unique(merged.urls),
        accounts=_unique(merged.accounts),
        orgs=_unique(merged.orgs),
        apps=_unique(merged.apps),
    )


def _unique(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for v in values:
        key = v.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(v.strip())
    return out


def _queries(
    phones: Iterable[str], urls: Iterable[str], domains: Iterable[str], accounts: Iterable[str]
) -> list[tuple[WatchlistType, str]]:
    """Every (type, normalised value) to look up, without duplicates."""
    pairs: list[tuple[WatchlistType, str]] = []
    pairs += [("PHONE", p) for p in phones]
    pairs += [("ACCOUNT", a) for a in accounts]
    for u in urls:
        pairs += [("URL", u), ("DOMAIN", normalise_domain(u))]
    pairs += [("DOMAIN", d) for d in domains]
    seen: set[tuple[WatchlistType, str]] = set()
    out = []
    for type_, raw in pairs:
        if not raw or not raw.strip():
            continue
        key = (type_, normalise_watchlist_value(type_, raw))
        if key[1].strip("+") and key not in seen:
            seen.add(key)
            out.append(key)
    return out


async def lookup_entities(
    state: StateRepo,
    *,
    phones: Iterable[str] = (),
    urls: Iterable[str] = (),
    domains: Iterable[str] = (),
    accounts: Iterable[str] = (),
) -> list[WatchlistMatch]:
    """Concurrent Firestore reads (one per value); one match per watchlist entry."""
    queries = _queries(phones, urls, domains, accounts)
    entries = await asyncio.gather(*(state.get_watchlist(t, v) for t, v in queries))
    matches: dict[tuple[str, str], WatchlistMatch] = {}
    for entry in entries:
        if entry is not None:
            matches.setdefault(
                (entry.type, entry.value),
                WatchlistMatch(
                    type=entry.type,
                    value=entry.value,
                    source=entry.source,
                    reported_count=entry.reported_count,
                ),
            )
    return list(matches.values())


async def lookup_all(state: StateRepo, entities: Entities) -> list[WatchlistMatch]:
    return await lookup_entities(
        state, phones=entities.phones, urls=entities.urls, accounts=entities.accounts
    )


@contextmanager
def use_state(state: StateRepo) -> Iterator[None]:
    """Make `state` the repo the `watchlist_lookup` tool reads (for this task and its children)."""
    token = _STATE.set(state)
    try:
        yield
    finally:
        _STATE.reset(token)


@contextmanager
def collecting() -> Iterator[list[WatchlistMatch]]:
    """Collect every match the `watchlist_lookup` tool returns inside the block, so matches an
    agent found reach the IntelResult through code, not through the model's answer."""
    found: list[WatchlistMatch] = []
    token = _FOUND.set(found)
    try:
        yield found
    finally:
        _FOUND.reset(token)


def _current_state() -> StateRepo:
    state = _STATE.get()
    if state is None:
        from app.data import get_state_repo

        state = get_state_repo()
        _STATE.set(state)
    return state


async def watchlist_lookup(
    phones: list[str] | None = None,
    urls: list[str] | None = None,
    domains: list[str] | None = None,
    accounts: list[str] | None = None,
) -> dict[str, object]:
    """Check phone numbers, URLs, domains and bank accounts against the bank's scam watchlist.

    Args:
        phones: Phone numbers, e.g. "+65 8000 0147".
        urls: Full URLs, e.g. "https://example.example/login". Their domains are checked too.
        domains: Bare domains, e.g. "example.example".
        accounts: Bank account numbers, e.g. "123-45678-9".

    Returns:
        {"matches": [{type, value, source, reported_count}], "checked": number of values looked up}
    """
    phones, urls, domains, accounts = phones or [], urls or [], domains or [], accounts or []
    matches = await lookup_entities(
        _current_state(), phones=phones, urls=urls, domains=domains, accounts=accounts
    )
    if (found := _FOUND.get()) is not None:
        found.extend(matches)
    return {
        "matches": [m.model_dump() for m in matches],
        "checked": len(_queries(phones, urls, domains, accounts)),
    }
