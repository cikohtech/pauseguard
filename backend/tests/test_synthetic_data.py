"""The generator is deterministic, the personas exist with their stories, and the scam
episodes follow the DATA_SPEC §2 playbooks."""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from app.data.seed import generate, personas, watchlist_entries
from tests.conftest import END_DATE, SEED

Rows = dict[str, list[dict[str, str]]]
PHONE = re.compile(r"^\+65 8000 0\d{3}$")


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def test_same_seed_gives_identical_files(seed_dir: Path, tmp_path: Path) -> None:
    generate(SEED, END_DATE, tmp_path)
    for name in (
        "customers.csv",
        "accounts.csv",
        "payees.csv",
        "transactions.csv",
        "personas.json",
    ):
        assert (tmp_path / name).read_bytes() == (seed_dir / name).read_bytes(), name


def test_other_seed_gives_other_data_but_same_personas(seed_dir: Path, tmp_path: Path) -> None:
    generate(SEED + 1, END_DATE, tmp_path)
    assert (tmp_path / "transactions.csv").read_bytes() != (
        seed_dir / "transactions.csv"
    ).read_bytes()
    assert (tmp_path / "personas.json").read_bytes() == (seed_dir / "personas.json").read_bytes()


def test_scale_and_mix(csv_rows: Rows) -> None:
    customers, txns = csv_rows["customers"], csv_rows["transactions"]
    assert len(customers) == 500
    assert 50_000 <= len(txns) <= 80_000
    assert 0.20 <= sum(int(c["age"]) >= 60 for c in customers) / 500 <= 0.30
    assert all(18 <= int(c["age"]) <= 85 for c in customers)
    langs = Counter(c["preferred_language"] for c in customers)
    assert langs["en"] > langs["zh"] > langs["ms"] > langs["ta"] > 0
    first, last = ts(txns[0]["ts"]), ts(txns[-1]["ts"])
    assert timedelta(days=360) < last - first <= timedelta(days=365)
    assert all(
        PHONE.match(c["trusted_contact_phone"]) for c in customers if c["trusted_contact_phone"]
    )
    phones = [c["trusted_contact_phone"] for c in customers if c["trusted_contact_phone"]]
    assert len(phones) == len(set(phones))


def test_personas_have_exact_ids_and_stories(csv_rows: Rows, seed_dir: Path) -> None:
    by_id = {c["customer_id"]: c for c in csv_rows["customers"]}
    assert by_id["cust_001"]["full_name"] == "Tan Mei Ling"
    assert (by_id["cust_001"]["age"], by_id["cust_001"]["preferred_language"]) == ("67", "zh")
    assert (by_id["cust_002"]["full_name"], by_id["cust_002"]["age"]) == ("Raj Kumar", "29")
    assert (by_id["cust_003"]["full_name"], by_id["cust_003"]["age"]) == ("Nur Aisyah", "34")
    assert "cust_004" not in by_id  # Daniel Lim is the analyst login, not a bank customer
    assert "son" in by_id["cust_001"]["trusted_contact_name"]  # "Call my son" on the RED screen

    balances = {a["customer_id"]: float(a["balance"]) for a in csv_rows["accounts"]}
    assert 40_000 <= balances["cust_001"] <= 44_000

    tan = [t for t in csv_rows["transactions"] if t["customer_id"] == "cust_001"]
    assert {t["category"] for t in tan if t["direction"] == "DEBIT"} == {"BILLS"}  # bills only
    tan_payees = [p for p in csv_rows["payees"] if p["customer_id"] == "cust_001"]
    assert all(p["dest_type"] == "MERCHANT" for p in tan_payees)
    assert not any(
        p["account_number"] == "123-45678-9"
        for p in csv_rows["payees"]
        if p["customer_id"] in ("cust_001", "cust_002", "cust_003")
    )

    aisyah_rent = [
        t
        for t in csv_rows["transactions"]
        if t["customer_id"] == "cust_003" and t["category"] == "RENT"
    ]
    assert len(aisyah_rent) >= 11  # pays her current landlord every month
    assert not any(
        t["is_scam_label"] == "true"
        for t in csv_rows["transactions"]
        if t["customer_id"] in ("cust_001", "cust_002", "cust_003")
    )

    loaded = personas(seed_dir)
    assert [p.customer_id for p in loaded] == ["cust_001", "cust_002", "cust_003"]
    assert "safe account" in loaded[0].story


def _episodes(rows: Rows) -> dict[tuple[str, str], list[dict[str, str]]]:
    out: dict[tuple[str, str], list[dict[str, str]]] = defaultdict(list)
    for t in rows["transactions"]:
        if t["is_scam_label"] == "true":
            out[(t["customer_id"], t["scam_typology_label"])].append(t)
    return out


def test_about_three_percent_of_customers_get_one_scam_episode(csv_rows: Rows) -> None:
    episodes = _episodes(csv_rows)
    victims = Counter(cid for cid, _ in episodes)
    assert 10 <= len(victims) <= 20  # ~3% of 497 generated customers
    assert max(victims.values()) == 1  # one typology each
    typologies = Counter(typ for _, typ in episodes)
    assert {"GOV_OFFICIAL_IMPERSONATION", "INVESTMENT", "JOB_TASK"} <= set(typologies)
    assert all(
        t["scam_typology_label"] for t in csv_rows["transactions"] if t["is_scam_label"] == "true"
    )
    assert not any(
        t["scam_typology_label"] for t in csv_rows["transactions"] if t["is_scam_label"] == "false"
    )


def test_scam_playbooks(csv_rows: Rows) -> None:
    payees = {p["payee_id"]: p for p in csv_rows["payees"]}
    seen = set()
    for (_, typology), txns in _episodes(csv_rows).items():
        dest = [payees[t["payee_id"]]["dest_type"] for t in txns]
        times = [ts(t["ts"]) for t in txns]
        amounts = [float(t["amount"]) for t in txns]
        for t in txns:  # every scam payment goes to a payee first paid by that very payment
            assert ts(payees[t["payee_id"]]["first_paid_at"]) <= ts(t["ts"])
        if typology == "GOV_OFFICIAL_IMPERSONATION":
            assert 1 <= len(txns) <= 3 and set(dest) == {"LOCAL_BANK"}
            assert max(times) - min(times) <= timedelta(hours=48)
            assert min(amounts) >= 1500  # large transfers
            seen.add(typology)
        elif typology == "INVESTMENT":
            assert len(txns) >= 3 and set(dest) == {"CRYPTO_EXCHANGE"}
            assert amounts == sorted(amounts)  # escalating
            seen.add(typology)
        elif typology == "JOB_TASK":
            assert len(txns) >= 3
            assert len({t["payee_id"] for t in txns}) == len(txns)  # a new payee every time
            assert amounts == sorted(amounts) and amounts[0] < 100  # small, then growing
            seen.add(typology)
    assert seen == {"GOV_OFFICIAL_IMPERSONATION", "INVESTMENT", "JOB_TASK"}


def test_hard_negatives_exist(csv_rows: Rows) -> None:
    """New payees and big amounts also happen without a scam, so neither alone decides."""
    payees = {p["payee_id"]: p for p in csv_rows["payees"]}
    legit_crypto = [
        t
        for t in csv_rows["transactions"]
        if t["payee_id"]
        and payees[t["payee_id"]]["dest_type"] == "CRYPTO_EXCHANGE"
        and t["is_scam_label"] == "false"
    ]
    assert legit_crypto
    first_payments = {p["payee_id"]: p["first_paid_at"] for p in csv_rows["payees"]}
    window_start = ts(csv_rows["transactions"][0]["ts"]) + timedelta(days=30)
    legit_new_payee = [
        t
        for t in csv_rows["transactions"]
        if t["payee_id"]
        and t["is_scam_label"] == "false"
        and first_payments[t["payee_id"]] == t["ts"]
        and ts(t["ts"]) > window_start
        and float(t["amount"]) >= 300
    ]
    assert len(legit_new_payee) >= 20
    never_paid = [p for p in csv_rows["payees"] if not p["first_paid_at"]]
    assert never_paid


def test_watchlist_seed_covers_the_demo_scenario(seed_dir: Path) -> None:
    raw = json.loads((seed_dir / "watchlist.json").read_text(encoding="utf-8"))["entries"]
    entries = watchlist_entries(seed_dir)
    assert 25 <= len(entries) <= 35
    assert {e.source for e in entries} == {"SEED"}
    values = {(e.type, e.value) for e in entries}
    assert ("PHONE", "+65 8000 0147") in values  # Mrs Tan's "MAS officer"
    assert ("ACCOUNT", "123-45678-9") in values  # her "safe account"
    assert not any("mas-gov-verify" in e.value for e in entries)  # left for Google Search
    assert {e.type for e in entries} == {"PHONE", "URL", "DOMAIN", "ACCOUNT"}
    for e in raw:
        if e["type"] == "PHONE":
            assert PHONE.match(e["value"])
        if e["type"] in ("URL", "DOMAIN"):
            assert re.search(r"\.example(/|$)", e["value"]), e["value"]


def test_personas_do_not_depend_on_dataset_size(csv_rows: Rows, tmp_path: Path) -> None:
    generate(SEED, END_DATE, tmp_path, customers=40)
    small = (tmp_path / "transactions.csv").read_text(encoding="utf-8").splitlines()[1:]
    persona_ids = {"cust_001", "cust_002", "cust_003"}
    personas_small = [line.split(",", 1)[1] for line in small if line.split(",")[1] in persona_ids]
    personas_full = [
        ",".join(list(t.values())[1:])
        for t in csv_rows["transactions"]
        if t["customer_id"] in persona_ids
    ]
    assert (
        personas_small and personas_small == personas_full
    )  # txn ids shift, the persona rows do not


def test_rejects_fewer_customers_than_personas(tmp_path: Path) -> None:
    with pytest.raises(SystemExit):
        generate(SEED, END_DATE, tmp_path, customers=2)
