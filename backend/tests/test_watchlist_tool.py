"""Watchlist tool: regex extraction, normalised lookups (a URL also checks its domain), and the
ADK tool's context-variable plumbing (state + collected matches)."""

from __future__ import annotations

import pytest

from app.data.memory_repo import MemoryStateRepo
from app.data.seed import seed_state
from app.models.schemas import Entities
from app.tools.watchlist import (
    collecting,
    entities_from_text,
    lookup_all,
    lookup_entities,
    merge_entities,
    use_state,
    watchlist_lookup,
)


@pytest.fixture
async def state() -> MemoryStateRepo:
    repo = MemoryStateRepo()
    await seed_state(repo)  # data/seed/watchlist.json
    return repo


def test_regex_finds_phones_accounts_and_urls() -> None:
    text = (
        "Officer Lee +65 8000 0147 says pay 123-45678-9 now. Verify at "
        "https://mas-gov-verify.example/case/2231, or call 8000 0112. "
        "Also see taskhub-rewards.example."
    )
    e = entities_from_text(text)
    assert e.phones == ["+65 8000 0147", "8000 0112"]
    assert e.accounts == ["123-45678-9"]
    assert e.urls == ["https://mas-gov-verify.example/case/2231", "taskhub-rewards.example"]


def test_regex_ignores_amounts_dates_emails_and_filenames() -> None:
    e = entities_from_text(
        "S$8,000 on 2026-10-11, ref 20261011, mail kelly@taskstar.example, file chat.png, 12.50"
    )
    assert e == Entities()


def test_regex_handles_chinese_text_and_several_inputs() -> None:
    e = entities_from_text("请转账到 556-208417-390，联系 +65 8000 0188。", None, "Call 8000 0188")
    assert e.accounts == ["556-208417-390"]
    assert e.phones == ["+65 8000 0188", "8000 0188"]  # same number, normalised at lookup


def test_merge_keeps_order_and_drops_duplicates() -> None:
    a = Entities(phones=["+65 8000 0147"], orgs=["MAS"], urls=["x.example"])
    b = Entities(phones=["+65 8000 0147", "8000 0112"], orgs=["mas", "SPF"], apps=["WhatsApp"])
    m = merge_entities(a, None, b)
    assert m.phones == ["+65 8000 0147", "8000 0112"]
    assert m.orgs == ["MAS", "SPF"]
    assert m.urls == ["x.example"] and m.apps == ["WhatsApp"]


async def test_lookup_normalises_and_dedupes(state: MemoryStateRepo) -> None:
    matches = await lookup_entities(
        state,
        phones=["+65 8000 0147", "80000147", "0065-8000-0147", "+65 9999 9999"],
        accounts=["123 45678 9", "999-99999-9"],
    )
    assert sorted((m.type, m.value, m.reported_count) for m in matches) == [
        ("ACCOUNT", "123456789", 4),
        ("PHONE", "+6580000147", 6),
    ]
    assert all(m.source == "SEED" for m in matches)


async def test_a_url_matches_its_listed_domain(state: MemoryStateRepo) -> None:
    matches = await lookup_entities(state, urls=["https://www.police-sg-case.example/case/77?x=1"])
    assert [(m.type, m.value) for m in matches] == [("DOMAIN", "police-sg-case.example")]


async def test_a_listed_url_and_domains(state: MemoryStateRepo) -> None:
    matches = await lookup_entities(
        state,
        urls=["https://parcel-redelivery-sg.example/pay-fee/"],
        domains=["QUANTAYIELD-VAULT.example", ""],
    )
    assert sorted((m.type, m.value) for m in matches) == [
        ("DOMAIN", "parcel-redelivery-sg.example"),
        ("DOMAIN", "quantayield-vault.example"),
        ("URL", "parcel-redelivery-sg.example/pay-fee"),
    ]


async def test_unknown_values_and_nothing_to_look_up(state: MemoryStateRepo) -> None:
    assert await lookup_entities(state, urls=["mas-gov-verify.example"]) == []  # deliberately new
    assert await lookup_entities(state) == []
    assert await lookup_all(state, Entities(phones=["+65 8000 0125"])) != []


async def test_tool_reads_state_from_context_and_reports_matches(state: MemoryStateRepo) -> None:
    with use_state(state), collecting() as found:
        out = await watchlist_lookup(phones=["+65 8000 0147"], urls=["mas-gov-verify.example"])
    assert out["checked"] == 3  # phone, URL, and the URL's domain
    assert [m["value"] for m in out["matches"]] == ["+6580000147"]  # type: ignore[index]
    assert [m.value for m in found] == ["+6580000147"]


async def test_tool_without_collector_still_answers(state: MemoryStateRepo) -> None:
    with use_state(state):
        out = await watchlist_lookup(accounts=["123-45678-9"])
    assert out["checked"] == 1 and len(out["matches"]) == 1  # type: ignore[arg-type]
