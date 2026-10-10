#!/usr/bin/env python3
"""Synthetic Harbour Bank data for PauseGuard (docs/DATA_SPEC.md §1-2).

    python data/generate/make_synthetic.py --seed 42 --out data/seed [--end-date 2026-10-10]

Writes customers.csv, accounts.csv, payees.csv, transactions.csv and personas.json.

Deterministic: the same --seed, --customers and --end-date always give byte-identical files.
Every customer has its own RNG (seeded from "<seed>:<customer_id>"), so the demo personas and
the other customers do not change when --customers does. --end-date defaults to today (SGT),
so a fresh seed always has a full 90-day window behind the live demo; history stops at
00:00 SGT on that date, so nothing is ever in the future.

Everything is fictional: "Harbour Bank" plus made-up banks, billers and exchanges, .example
domains, and phone numbers in +65 8000 0xxx, allocated as:
    0001-0199  scam side (data/seed/watchlist.json, eval scammers)
    0200-0299  legit businesses (eval set)
    0300-0309  persona trusted contacts
    0310-0999  generated trusted contacts

Stdlib only, so it runs with any Python 3.12.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta, timezone
from pathlib import Path

SGT = timezone(timedelta(hours=8))
HISTORY_DAYS = 365
SCAM_SHARE = 0.03  # share of generated customers with one scam episode
HARBOUR = "Harbour Bank"
TS_FORMAT = "%Y-%m-%d %H:%M:%S+00:00"  # UTC; BigQuery CSV loads it, SQLite sorts it as text

# --- Fictional institutions -------------------------------------------------------------------

LOCAL_BANKS = [
    "Orchid Trust Bank",
    "Kampong Federal Bank",
    "Riverside Savings Bank",
    "Lantern Commerce Bank",
]
OVERSEAS_BANKS = [
    ("Bunga Raya Mutual Bank", "MY"),
    ("Peacock Rural Bank", "IN"),
    ("Sampaguita Savings", "PH"),
    ("Lotus River Bank", "CN"),
    ("Komodo Citra Bank", "ID"),
]
UTILITY = "City Power & Water"
TELCOS = ["Kite Mobile", "Equator Telecom", "Nova Fibre Broadband"]
TOWN_COUNCIL = "Town Council (S&CC)"
INSURERS = ["Evergreen Life Assurance", "Bluewater General Insurance"]
BROKERS = ["Tidewater Securities", "Keystone Invest Brokerage"]
LEGIT_CRYPTO = "Nimbus Crypto Exchange"
SCAM_CRYPTO = ["QuantaYield Digital Vault", "BitLagoon Wallet", "AuroraMint Exchange"]
SUPPLIERS = [
    "Sinar Wholesale Trading",
    "Golden Grain Supplies",
    "Jurong Packaging Works",
    "Eastline Logistics",
    "Prima Kitchen Equipment",
    "Bayview Printing Services",
]
OVERSEAS_SUPPLIERS = [
    "Selangor Fabrics Sdn Bhd",
    "Guangzhou Lantern Trading Co",
    "Manila Bay Exports Inc",
]
LEGIT_ONE_OFFS = [  # (payee name, category, min, max) for hard negatives: new payee, legit
    ("Ah Seng Renovation Works", "TRANSFER", 1500, 6000),
    ("Bright Minds Tuition Centre", "BILLS", 300, 1200),
    ("Harmony Movers", "TRANSFER", 400, 1200),
    ("Sunrise Wedding Planner", "TRANSFER", 1000, 5000),
    ("Pawsome Vet Clinic", "BILLS", 200, 1500),
    ("Greenleaf Aircon Servicing", "BILLS", 150, 600),
    ("Kindred Hearts Charity", "TRANSFER", 50, 500),
    ("Dr Wong Family Dental", "BILLS", 200, 1800),
]
GOV_MULE_NAMES = [
    "Safe Custody Acct",
    "Case Holding Acct",
    "Investigation Escrow Acct",
    "Asset Protection Acct",
]

# --- Names (combined at random, so they describe no one; persona names are left out) ---------

# fmt: off
CN_SURNAMES = ["Tan", "Lim", "Lee", "Ng", "Ong", "Wong", "Goh", "Chua", "Chan", "Koh", "Teo",
    "Ang", "Yeo", "Tay", "Ho", "Low", "Toh", "Sim", "Chong", "Chia"]
CN_GIVEN = ["Wei Jie", "Jun Hao", "Hui Min", "Xin Yi", "Kah Seng", "Siew Hwa", "Boon Keng",
    "Li Ting", "Zhi Hao", "Shu Fen", "Choon Hock", "Yu Xuan", "Kok Wai", "Pei Shan", "Jia Hui",
    "Wen Jun", "Soo Lin", "Beng Huat", "Geok Eng"]
EN_GIVEN = ["Daniel", "Sarah", "Marcus", "Rachel", "Joshua", "Michelle", "Ryan", "Natalie",
    "Adrian", "Clara", "Benjamin", "Grace"]
MS_GIVEN = ["Muhammad Hafiz", "Siti Aminah", "Ahmad Faizal", "Farah Nadia", "Mohd Rizal",
    "Nur Hidayah", "Syafiq", "Haziq", "Norhayati", "Rahimah", "Iskandar", "Aqilah", "Zainal"]
MS_PARENT = ["Rahman", "Ismail", "Hassan", "Osman", "Yusof", "Salleh", "Abdullah", "Ibrahim",
    "Kassim", "Hamid"]
TA_GIVEN = ["Arun", "Priya", "Kavitha", "Suresh", "Lakshmi", "Vikram", "Deepa", "Ganesh", "Meena",
    "Ravi", "Anita", "Karthik", "Nisha", "Bala", "Shanti"]
TA_SURNAMES = ["Kumar", "Pillai", "Nair", "Raman", "Krishnan", "Subramaniam", "Menon", "Rajan",
    "Naidu", "Govind"]
EURASIAN_SURNAMES = ["De Souza", "Pereira", "Fernandez", "Rodrigues", "Carvalho", "Sequeira",
    "D'Cruz"]
# fmt: on


def person_name(rng: random.Random, language: str) -> str:
    style = language
    if language == "en":
        style = rng.choices(["zh", "en_zh", "ms", "ta", "eurasian"], [30, 20, 20, 20, 10])[0]
    if style == "zh":
        return f"{rng.choice(CN_SURNAMES)} {rng.choice(CN_GIVEN)}"
    if style == "en_zh":
        return f"{rng.choice(EN_GIVEN)} {rng.choice(CN_SURNAMES)}"
    if style == "ms":
        return f"{rng.choice(MS_GIVEN)} {rng.choice(MS_PARENT)}"
    if style == "ta":
        return f"{rng.choice(TA_GIVEN)} {rng.choice(TA_SURNAMES)}"
    return f"{rng.choice(EN_GIVEN)} {rng.choice(EURASIAN_SURNAMES)}"


def account_number(rng: random.Random, bank: str) -> str:
    """Digits, dashes and (overseas) a country prefix only: the repos normalise on that basis."""
    if bank == HARBOUR:
        return f"{rng.randint(100, 999)}-{rng.randint(10000, 99999)}-{rng.randint(0, 9)}"
    for name, country in OVERSEAS_BANKS:
        if bank == name:
            digits = f"{rng.randint(10, 99)} {rng.randint(1000, 9999)} {rng.randint(1000, 9999)}"
            return f"{country}{digits}"
    return f"{rng.randint(100, 999)}-{rng.randint(100000, 999999)}-{rng.randint(100, 999)}"


def fmt_ts(dt: datetime | None) -> str:
    return dt.astimezone(UTC).strftime(TS_FORMAT) if dt else ""


# --- Personas (DATA_SPEC §2; exact IDs). cust_004 is the analyst, not a bank customer. ---------

PERSONAS = {
    "cust_001": {
        "full_name": "Tan Mei Ling",
        "age": 67,
        "preferred_language": "zh",
        "segment": "RETIREE",
        "trusted_contact_name": "Tan Jun Hao (son)",
        "trusted_contact_phone": "+65 8000 0300",
        "balance": 42180.55,
        "story": "Retiree who only pays bills. A fake MAS officer tells her to move S$8,000 to "
        "a 'safe account' (new payee 'Lee Wei Investigation Acct', 123-45678-9).",
    },
    "cust_002": {
        "full_name": "Raj Kumar",
        "age": 29,
        "preferred_language": "en",
        "segment": "WORKER",
        "trusted_contact_name": "Priya Kumar (sister)",
        "trusted_contact_phone": "+65 8000 0301",
        "balance": 2340.20,
        "story": "Gig worker. A Telegram 'recruiter' asks for a S$450 top-up to a new payee to "
        "unlock his task commission (job-task scam).",
    },
    "cust_003": {
        "full_name": "Nur Aisyah",
        "age": 34,
        "preferred_language": "en",
        "segment": "WORKER",
        "trusted_contact_name": "Ahmad Hakim (husband)",
        "trusted_contact_phone": "+65 8000 0302",
        "balance": 18640.75,
        "story": "Teacher moving flat. Pays a S$3,200 deposit to her new landlord and shares the "
        "tenancy agreement (legitimate payment).",
    },
}
ANALYST_ID = "cust_004"  # Daniel Lim: Firebase Auth analyst login for the console


# --- Model ------------------------------------------------------------------------------------


@dataclass
class Profile:
    customer_id: str
    full_name: str
    age: int
    language: str
    segment: str
    balance: float
    created_at: datetime
    trusted_name: str | None = None
    trusted_phone: str | None = None


@dataclass
class PayeeRow:
    payee_id: str
    customer_id: str
    payee_name: str
    account_number: str
    bank_name: str
    country: str
    dest_type: str
    created_at: datetime
    first_paid_at: datetime | None = None


@dataclass
class TxnRow:
    customer_id: str
    account_id: str
    payee: PayeeRow | None
    amount: float
    direction: str
    category: str
    ts: datetime
    scam_typology: str | None = None


@dataclass
class World:
    start: date
    end: date
    customers: list[Profile] = field(default_factory=list)
    payees: list[PayeeRow] = field(default_factory=list)
    txns: list[TxnRow] = field(default_factory=list)
    _payee_seq: int = 0

    @property
    def window_start(self) -> datetime:
        return datetime.combine(self.start, time(0), SGT)

    @property
    def window_end(self) -> datetime:
        return datetime.combine(self.end, time(0), SGT)

    def new_payee(
        self,
        cust: Profile,
        name: str,
        dest_type: str,
        created_at: datetime,
        rng: random.Random,
        bank: str | None = None,
        country: str = "SG",
    ) -> PayeeRow:
        if bank is None:
            if dest_type == "OVERSEAS":
                bank, country = rng.choice(OVERSEAS_BANKS)
            elif dest_type == "CRYPTO_EXCHANGE":
                bank = name
            else:
                bank = HARBOUR if rng.random() < 0.4 else rng.choice(LOCAL_BANKS)
        self._payee_seq += 1
        p = PayeeRow(
            f"pay_{self._payee_seq:05d}",
            cust.customer_id,
            name,
            account_number(rng, bank),
            bank,
            country,
            dest_type,
            created_at,
        )
        self.payees.append(p)
        return p

    def debit(
        self,
        cust: Profile,
        amount: float,
        category: str,
        ts: datetime,
        payee: PayeeRow | None = None,
        scam: str | None = None,
    ) -> None:
        self.add(cust, amount, "DEBIT", category, ts, payee, scam)

    def credit(self, cust: Profile, amount: float, category: str, ts: datetime) -> None:
        self.add(cust, amount, "CREDIT", category, ts)

    def add(
        self,
        cust: Profile,
        amount: float,
        direction: str,
        category: str,
        ts: datetime,
        payee: PayeeRow | None = None,
        scam: str | None = None,
    ) -> None:
        if not (self.window_start <= ts < self.window_end):
            return
        self.txns.append(
            TxnRow(
                cust.customer_id,
                account_id(cust.customer_id),
                payee,
                round(amount, 2),
                direction,
                category,
                ts,
                scam,
            )
        )


def account_id(customer_id: str) -> str:
    return "acc_" + customer_id.removeprefix("cust_")


def at(day: date, rng: random.Random, hours: tuple[int, int] = (8, 22)) -> datetime:
    """A local (SGT) time on `day`, hour drawn from [hours[0], hours[1]]; ~2% late-night."""
    hour = rng.randint(0, 5) if rng.random() < 0.02 else rng.randint(*hours)
    return datetime.combine(day, time(hour, rng.randint(0, 59), rng.randint(0, 59)), SGT)


def on(month: date, day: int, rng: random.Random, hours: tuple[int, int] = (8, 22)) -> datetime:
    """`at()` on a given day of `month`."""
    return at(month.replace(day=day), rng, hours)


def months(start: date, end: date) -> list[date]:
    """First day of every calendar month that overlaps [start, end)."""
    out, cur = [], start.replace(day=1)
    while cur < end:
        out.append(cur)
        cur = (cur + timedelta(days=32)).replace(day=1)
    return out


def day_in(month: date, rng: random.Random) -> date:
    nxt = (month + timedelta(days=32)).replace(day=1)
    return month + timedelta(days=rng.randrange((nxt - month).days))


# --- Normal behaviour -------------------------------------------------------------------------


def make_profile(rng: random.Random, cid: str, end: date, phone_pool: list[str]) -> Profile:
    age = rng.randint(60, 85) if rng.random() < 0.25 else rng.randint(18, 59)
    language = rng.choices(["en", "zh", "ms", "ta"], [55, 30, 10, 5])[0]
    if age >= 62:
        segment = "RETIREE" if rng.random() < 0.8 else "WORKER"
    elif age <= 24:
        segment = "STUDENT" if rng.random() < 0.6 else "WORKER"
    else:
        segment = "SME_OWNER" if rng.random() < 0.15 else "WORKER"
    balance = {
        "RETIREE": rng.lognormvariate(10.3, 0.9),
        "STUDENT": rng.lognormvariate(7.3, 0.7),
        "WORKER": rng.lognormvariate(9.4, 0.9),
        "SME_OWNER": rng.lognormvariate(10.6, 0.9),
    }[segment]
    created = datetime.combine(end - timedelta(days=rng.randint(400, 5000)), time(10), SGT)
    cust = Profile(
        cid,
        person_name(rng, language),
        age,
        language,
        segment,
        round(min(balance, 600_000), 2),
        created,
    )
    if phone_pool and rng.random() < (0.85 if age >= 60 else 0.3):
        relation = (
            rng.choice(["son", "daughter"])
            if age >= 60
            else rng.choice(["mother", "father", "sister", "brother", "spouse"])
        )
        name = (
            f"{cust.full_name.split()[0]} {rng.choice(CN_GIVEN)}"
            if language == "zh"
            else person_name(rng, language)
        )  # Chinese families share the surname
        cust.trusted_name = f"{name} ({relation})"
        cust.trusted_phone = phone_pool.pop(0)
    return cust


def normal_life(w: World, cust: Profile, rng: random.Random) -> None:
    """Twelve months of ordinary banking: income, bills, card spend, transfers, investments."""
    seg, before = cust.segment, w.window_start - timedelta(days=rng.randint(30, 900))

    def payee(name: str, dest: str, **kw: object) -> PayeeRow:
        return w.new_payee(cust, name, dest, before, rng, **kw)  # type: ignore[arg-type]

    utility = payee(UTILITY, "MERCHANT")
    telco = payee(rng.choice(TELCOS), "MERCHANT")
    town = payee(TOWN_COUNCIL, "MERCHANT") if rng.random() < 0.75 else None
    insurer = payee(rng.choice(INSURERS), "MERCHANT") if rng.random() < 0.5 else None
    rents = (
        seg in ("WORKER", "STUDENT")
        and cust.age < 45
        and rng.random() < (0.45 if seg == "WORKER" else 0.15)
    )
    landlord = (
        payee(person_name(rng, "en"), rng.choice(["LOCAL_BANK", "PAYNOW"])) if rents else None
    )
    rent = rng.uniform(800, 3200) if seg == "WORKER" else rng.uniform(500, 1000)
    family = [
        payee(person_name(rng, cust.language), rng.choice(["LOCAL_BANK", "PAYNOW"]))
        for _ in range(rng.randint(0, 2) if seg != "STUDENT" else 0)
    ]
    overseas_family = (
        payee(person_name(rng, cust.language), "OVERSEAS")
        if seg == "WORKER" and rng.random() < 0.08
        else None
    )
    friends = [payee(person_name(rng, "en"), "PAYNOW") for _ in range(rng.randint(1, 4))]
    broker = (
        payee(rng.choice(BROKERS), "LOCAL_BANK")
        if seg != "STUDENT" and rng.random() < 0.3
        else None
    )
    crypto = (
        payee(LEGIT_CRYPTO, "CRYPTO_EXCHANGE")
        if seg == "WORKER" and cust.age < 45 and rng.random() < 0.06
        else None
    )
    suppliers = (
        [payee(n, "LOCAL_BANK") for n in rng.sample(SUPPLIERS, rng.randint(2, 4))]
        if seg == "SME_OWNER"
        else []
    )
    overseas_supplier = (
        payee(rng.choice(OVERSEAS_SUPPLIERS), "OVERSEAS")
        if seg == "SME_OWNER" and rng.random() < 0.3
        else None
    )
    if rng.random() < 0.1:  # added once, never paid: first_paid_at stays empty
        payee(person_name(rng, "en"), "PAYNOW")

    salary = {
        "WORKER": rng.uniform(2200, 9000),
        "RETIREE": rng.uniform(600, 1800),
        "STUDENT": rng.uniform(300, 900),
        "SME_OWNER": 0.0,
    }[seg]
    family_gift = rng.uniform(200, 1200)
    invest = rng.uniform(200, 2000)
    rent_day, salary_day = rng.randint(1, 5), rng.randint(25, 28)

    for m in months(w.start, w.end):
        # Income
        if seg == "SME_OWNER":
            for _ in range(rng.randint(2, 5)):
                w.credit(cust, rng.uniform(1000, 15000), "TRANSFER", at(day_in(m, rng), rng))
        elif seg == "STUDENT":
            w.credit(cust, salary, "FAMILY", on(m, 1, rng))
            if rng.random() < 0.3:
                w.credit(cust, rng.uniform(400, 1200), "SALARY", on(m, salary_day, rng))
        else:
            w.credit(
                cust,
                salary * rng.uniform(0.97, 1.03),
                "SALARY",
                on(m, 1 if seg == "RETIREE" else salary_day, rng, (6, 9)),
            )
        # Bills
        w.debit(cust, rng.uniform(50, 180), "BILLS", on(m, rng.randint(10, 20), rng), utility)
        w.debit(cust, rng.uniform(20, 60), "BILLS", on(m, rng.randint(5, 15), rng), telco)
        if town:
            w.debit(cust, rng.uniform(20, 90), "BILLS", on(m, rng.randint(1, 10), rng), town)
        if insurer:
            w.debit(cust, rng.uniform(60, 300), "BILLS", on(m, rng.randint(1, 28), rng), insurer)
        if landlord:
            w.debit(cust, rent, "RENT", on(m, rent_day, rng), landlord)
        # Card spend (no payee)
        for _ in range(rng.randint(2, 5)):
            w.debit(cust, rng.uniform(15, 180), "GROCERIES", at(day_in(m, rng), rng))
        for _ in range(rng.randint(0, 3)):
            w.debit(cust, rng.uniform(10, 400), "SHOPPING", at(day_in(m, rng), rng))
        # Transfers
        for fam in family:
            if rng.random() < 0.7:
                w.debit(
                    cust,
                    family_gift * rng.uniform(0.8, 1.2),
                    "FAMILY",
                    on(m, rng.randint(26, 28), rng),
                    fam,
                )
        if overseas_family:
            w.debit(cust, rng.uniform(200, 800), "FAMILY", at(day_in(m, rng), rng), overseas_family)
        for _ in range(rng.randint(0, 2)):
            w.debit(
                cust, rng.uniform(10, 150), "TRANSFER", at(day_in(m, rng), rng), rng.choice(friends)
            )
        if broker and rng.random() < 0.6:
            w.debit(
                cust, invest * rng.uniform(0.5, 1.5), "INVESTMENT", at(day_in(m, rng), rng), broker
            )
        if crypto and rng.random() < 0.5:
            w.debit(cust, rng.uniform(50, 500), "INVESTMENT", at(day_in(m, rng), rng), crypto)
        for sup in suppliers:
            w.debit(cust, rng.uniform(500, 8000), "TRANSFER", at(day_in(m, rng), rng), sup)
        if overseas_supplier and rng.random() < 0.5:
            w.debit(
                cust,
                rng.uniform(1000, 12000),
                "TRANSFER",
                at(day_in(m, rng), rng),
                overseas_supplier,
            )

    # Legit spikes, so a big amount alone is not a scam: big card purchases ...
    if rng.random() < 0.25:
        for _ in range(rng.randint(1, 2)):
            w.debit(cust, rng.uniform(600, 3500), "SHOPPING", at(random_day(w, rng), rng))
    # ... and hard negatives: a one-off payment to a brand-new payee.
    if rng.random() < 0.15:
        name, category, lo, hi = rng.choice(LEGIT_ONE_OFFS)
        ts = at(random_day(w, rng), rng)
        p = w.new_payee(
            cust,
            name,
            rng.choice(["LOCAL_BANK", "PAYNOW"]),
            ts - timedelta(minutes=rng.randint(5, 60 * 24 * 3)),
            rng,
        )
        w.debit(cust, rng.uniform(lo, hi), category, ts, p)


def random_day(w: World, rng: random.Random, margin_days: int = 0) -> date:
    return w.start + timedelta(days=rng.randrange((w.end - w.start).days - margin_days))


# --- Scam episodes (DATA_SPEC §2 playbooks) ---------------------------------------------------

# One full cycle of typologies; the list repeats if there are more victims.
SCAM_CYCLE = [
    "GOV_OFFICIAL_IMPERSONATION",
    "INVESTMENT",
    "JOB_TASK",
    "GOV_OFFICIAL_IMPERSONATION",
    "INVESTMENT",
    "JOB_TASK",
    "ECOMMERCE",
    "GOV_OFFICIAL_IMPERSONATION",
    "FAKE_FRIEND",
    "INVESTMENT",
    "JOB_TASK",
    "GOV_OFFICIAL_IMPERSONATION",
    "ROMANCE",
    "ECOMMERCE",
    "BEC_INVOICE",
]
ELIGIBLE = {
    "GOV_OFFICIAL_IMPERSONATION": lambda c: c.age >= 50,
    "JOB_TASK": lambda c: c.age <= 40,
    "ROMANCE": lambda c: c.age >= 35,
    "BEC_INVOICE": lambda c: c.segment == "SME_OWNER",
}


def scam_hour_time(day: date, rng: random.Random, night_share: float) -> datetime:
    hour = rng.randint(0, 5) if rng.random() < night_share else rng.randint(10, 23)
    return datetime.combine(day, time(hour, rng.randint(0, 59), rng.randint(0, 59)), SGT)


def inject_scam(w: World, cust: Profile, typology: str, rng: random.Random) -> None:
    span = {"INVESTMENT": 60, "ROMANCE": 120}.get(typology, 5)
    day0 = w.start + timedelta(days=rng.randint(30, (w.end - w.start).days - span - 2))
    t0 = scam_hour_time(day0, rng, 0.5 if typology == "GOV_OFFICIAL_IMPERSONATION" else 0.2)

    def mule(name: str, dest: str, ts: datetime) -> PayeeRow:
        return w.new_payee(cust, name, dest, ts - timedelta(minutes=rng.randint(2, 30)), rng)

    if typology == "GOV_OFFICIAL_IMPERSONATION":
        # New LOCAL_BANK payee, 1-3 large transfers within 48 h, often at night.
        p = mule(rng.choice(GOV_MULE_NAMES + [person_name(rng, "zh")]), "LOCAL_BANK", t0)
        n = rng.randint(1, 3)
        each = max(2000.0, cust.balance * rng.uniform(0.3, 0.9) / n)
        for i in range(n):
            ts = t0 + timedelta(hours=rng.uniform(0, 47) if i else 0)
            w.debit(cust, round(each * rng.uniform(0.85, 1.15), -1), "TRANSFER", ts, p, typology)
    elif typology == "INVESTMENT":
        # Escalating transfers to a new CRYPTO_EXCHANGE payee (sometimes a second one).
        p = mule(rng.choice(SCAM_CRYPTO), "CRYPTO_EXCHANGE", t0)
        amount, ts = rng.uniform(300, 1500), t0
        for i in range(rng.randint(3, 6)):
            if i == 3 and rng.random() < 0.5:
                p = mule(rng.choice(SCAM_CRYPTO), "CRYPTO_EXCHANGE", ts)
            w.debit(cust, round(amount, -1), "INVESTMENT", ts, p, typology)
            amount *= rng.uniform(1.5, 2.4)
            ts = scam_hour_time(ts.date() + timedelta(days=rng.randint(4, 12)), rng, 0.2)
    elif typology == "JOB_TASK":
        # Small, then growing top-ups, each to a different new payee, within a few days.
        amount, ts = rng.uniform(20, 60), t0
        for _ in range(rng.randint(3, 6)):
            p = mule(person_name(rng, "en"), rng.choice(["PAYNOW", "LOCAL_BANK"]), ts)
            w.debit(cust, amount, "TRANSFER", ts, p, typology)
            amount *= rng.uniform(1.8, 2.6)
            ts += timedelta(hours=rng.uniform(2, 20))
    elif typology == "ECOMMERCE":
        p = mule(person_name(rng, "en"), "PAYNOW", t0)
        w.debit(cust, rng.uniform(80, 900), "SHOPPING", t0, p, typology)
    elif typology == "FAKE_FRIEND":
        p = mule(person_name(rng, cust.language), "LOCAL_BANK", t0)
        for i in range(rng.randint(1, 2)):
            w.debit(
                cust,
                rng.uniform(500, 3000),
                "TRANSFER",
                t0 + timedelta(hours=rng.uniform(1, 6) * i),
                p,
                typology,
            )
    elif typology == "ROMANCE":
        p = mule(person_name(rng, "en"), "OVERSEAS", t0)
        ts = t0
        for _ in range(rng.randint(3, 5)):
            w.debit(cust, rng.uniform(800, 6000), "TRANSFER", ts, p, typology)
            ts = scam_hour_time(ts.date() + timedelta(days=rng.randint(15, 30)), rng, 0.3)
    elif typology == "BEC_INVOICE":
        # A known supplier's name with new bank details.
        known = [
            p for p in w.payees if p.customer_id == cust.customer_id and p.payee_name in SUPPLIERS
        ]
        name = known[0].payee_name if known else rng.choice(SUPPLIERS)
        p = mule(name, "LOCAL_BANK", t0)
        w.debit(cust, rng.uniform(3000, 25000), "TRANSFER", t0, p, typology)


# --- Personas: hand-shaped histories ----------------------------------------------------------


def persona_profile(cid: str, end: date) -> Profile:
    p = PERSONAS[cid]
    return Profile(
        cid,
        p["full_name"],
        p["age"],
        p["preferred_language"],
        p["segment"],
        p["balance"],
        datetime.combine(end - timedelta(days=3650), time(10), SGT),
        p["trusted_contact_name"],
        p["trusted_contact_phone"],
    )


def persona_life(w: World, cust: Profile, rng: random.Random) -> None:
    before = w.window_start - timedelta(days=400)

    def payee(name: str, dest: str, **kw: object) -> PayeeRow:
        return w.new_payee(cust, name, dest, before, rng, **kw)  # type: ignore[arg-type]

    if cust.customer_id == "cust_001":
        # Mrs Tan: monthly retirement payout, four bills, nothing else. No new payees.
        utility, telco = payee(UTILITY, "MERCHANT", bank=HARBOUR), payee("Kite Mobile", "MERCHANT")
        town, insurer = (
            payee(TOWN_COUNCIL, "MERCHANT"),
            payee("Evergreen Life Assurance", "MERCHANT"),
        )
        for m in months(w.start, w.end):
            w.credit(cust, 1180.00, "SALARY", on(m, 1, rng, (7, 8)))
            w.debit(cust, rng.uniform(70, 140), "BILLS", on(m, 12, rng, (9, 11)), utility)
            w.debit(cust, 28.90, "BILLS", on(m, 8, rng, (9, 11)), telco)
            w.debit(cust, 43.50, "BILLS", on(m, 3, rng, (9, 11)), town)
            w.debit(cust, 126.00, "BILLS", on(m, 20, rng, (9, 11)), insurer)
    elif cust.customer_id == "cust_002":
        # Raj: weekly ride-hail payouts, rent share, small spend and PayNow splits.
        landlord = payee("Chua Siew Lan", "PAYNOW")
        mother = payee("Kumari Ramasamy", "PAYNOW")
        telco = payee("Equator Telecom", "MERCHANT")
        friends = [payee(n, "PAYNOW") for n in ("Arun Nair", "Marcus Teo", "Haziq Osman")]
        day = w.start
        while day < w.end:
            if day.weekday() == 0:
                w.credit(cust, rng.uniform(250, 520), "SALARY", at(day, rng, (6, 8)))
            if rng.random() < 0.18:
                w.debit(cust, rng.uniform(8, 60), "GROCERIES", at(day, rng, (11, 22)))
            if rng.random() < 0.05:
                w.debit(
                    cust,
                    rng.uniform(10, 45),
                    "TRANSFER",
                    at(day, rng, (12, 23)),
                    rng.choice(friends),
                )
            if day.day == 2:
                w.debit(cust, 750.00, "RENT", at(day, rng, (9, 12)), landlord)
            if day.day == 10:
                w.debit(cust, 35.00, "BILLS", at(day, rng, (9, 12)), telco)
            if day.day == 28:
                w.debit(cust, 300.00, "FAMILY", at(day, rng, (18, 21)), mother)
            day += timedelta(days=1)
    elif cust.customer_id == "cust_003":
        # Aisyah: teacher's salary, rent to her current landlord, bills, a monthly broker plan.
        landlord = payee("Koh Residences Pte Ltd", "LOCAL_BANK", bank="Orchid Trust Bank")
        mother = payee("Salmah Ismail", "LOCAL_BANK", bank=HARBOUR)
        broker = payee("Tidewater Securities", "LOCAL_BANK", bank="Riverside Savings Bank")
        utility, telco = payee(UTILITY, "MERCHANT"), payee("Nova Fibre Broadband", "MERCHANT")
        insurer = payee("Bluewater General Insurance", "MERCHANT")
        friends = [payee(n, "PAYNOW") for n in ("Farah Nadia Yusof", "Clara Pereira")]
        for m in months(w.start, w.end):
            w.credit(cust, 5150.00, "SALARY", on(m, 25, rng, (6, 8)))
            w.debit(cust, 2400.00, "RENT", on(m, 1, rng, (8, 10)), landlord)
            w.debit(cust, 500.00, "FAMILY", on(m, 26, rng, (19, 21)), mother)
            w.debit(cust, 300.00, "INVESTMENT", on(m, 27, rng, (9, 11)), broker)
            w.debit(cust, rng.uniform(60, 130), "BILLS", on(m, 14, rng), utility)
            w.debit(cust, 49.90, "BILLS", on(m, 9, rng), telco)
            w.debit(cust, 88.00, "BILLS", on(m, 18, rng), insurer)
            for _ in range(rng.randint(3, 5)):
                w.debit(cust, rng.uniform(20, 140), "GROCERIES", at(day_in(m, rng), rng))
            for _ in range(rng.randint(1, 3)):
                w.debit(cust, rng.uniform(15, 220), "SHOPPING", at(day_in(m, rng), rng))
            if rng.random() < 0.6:
                w.debit(
                    cust,
                    rng.uniform(12, 80),
                    "TRANSFER",
                    at(day_in(m, rng), rng),
                    rng.choice(friends),
                )


# --- Build + write ----------------------------------------------------------------------------


def build(seed: int, n_customers: int, end: date) -> World:
    w = World(start=end - timedelta(days=HISTORY_DAYS), end=end)
    phone_pool = [f"+65 8000 0{n:03d}" for n in range(310, 1000)]

    for cid in PERSONAS:
        cust = persona_profile(cid, end)
        w.customers.append(cust)
        persona_life(w, cust, random.Random(f"{seed}:{cid}"))

    generated: list[Profile] = []
    for i in range(n_customers - len(PERSONAS)):
        cid = f"cust_{i + 5:03d}"  # cust_004 is reserved for the analyst
        rng = random.Random(f"{seed}:{cid}")
        cust = make_profile(rng, cid, end, phone_pool)
        w.customers.append(cust)
        generated.append(cust)
        normal_life(w, cust, rng)

    pick = random.Random(f"{seed}:scam-victims")
    victims: set[str] = set()
    for i in range(round(SCAM_SHARE * len(generated))):
        typology = SCAM_CYCLE[i % len(SCAM_CYCLE)]
        ok = ELIGIBLE.get(typology, lambda c: True)
        pool = [c for c in generated if c.customer_id not in victims and ok(c)] or [
            c for c in generated if c.customer_id not in victims
        ]
        victim = pick.choice(pool)
        victims.add(victim.customer_id)
        inject_scam(w, victim, typology, random.Random(f"{seed}:{victim.customer_id}:scam"))

    for p in w.payees:  # first_paid_at = first debit to that payee (None if never paid)
        p.first_paid_at = None
    for t in w.txns:
        if (
            t.payee
            and t.direction == "DEBIT"
            and (t.payee.first_paid_at is None or t.ts < t.payee.first_paid_at)
        ):
            t.payee.first_paid_at = t.ts
    w.txns.sort(key=lambda t: (t.ts.astimezone(UTC), t.customer_id, t.amount))
    return w


def write(w: World, out: Path) -> dict[str, int]:
    out.mkdir(parents=True, exist_ok=True)

    def dump(name: str, header: list[str], rows: list[list[object]]) -> None:
        with (out / name).open("w", newline="", encoding="utf-8") as f:
            wr = csv.writer(f, lineterminator="\n")
            wr.writerow(header)
            wr.writerows(rows)

    dump(
        "customers.csv",
        [
            "customer_id",
            "full_name",
            "age",
            "preferred_language",
            "segment",
            "trusted_contact_name",
            "trusted_contact_phone",
            "created_at",
        ],
        [
            [
                c.customer_id,
                c.full_name,
                c.age,
                c.language,
                c.segment,
                c.trusted_name or "",
                c.trusted_phone or "",
                fmt_ts(c.created_at),
            ]
            for c in w.customers
        ],
    )
    dump(
        "accounts.csv",
        ["account_id", "customer_id", "balance", "currency", "opened_at"],
        [
            [
                account_id(c.customer_id),
                c.customer_id,
                f"{c.balance:.2f}",
                "SGD",
                fmt_ts(c.created_at),
            ]
            for c in w.customers
        ],
    )
    dump(
        "payees.csv",
        [
            "payee_id",
            "customer_id",
            "payee_name",
            "account_number",
            "bank_name",
            "country",
            "dest_type",
            "first_paid_at",
            "created_at",
        ],
        [
            [
                p.payee_id,
                p.customer_id,
                p.payee_name,
                p.account_number,
                p.bank_name,
                p.country,
                p.dest_type,
                fmt_ts(p.first_paid_at),
                fmt_ts(p.created_at),
            ]
            for p in w.payees
        ],
    )
    dump(
        "transactions.csv",
        [
            "txn_id",
            "customer_id",
            "account_id",
            "payee_id",
            "amount",
            "currency",
            "direction",
            "category",
            "ts",
            "is_scam_label",
            "scam_typology_label",
        ],
        [
            [
                f"txn_{i:06d}",
                t.customer_id,
                t.account_id,
                t.payee.payee_id if t.payee else "",
                f"{t.amount:.2f}",
                "SGD",
                t.direction,
                t.category,
                fmt_ts(t.ts),
                "true" if t.scam_typology else "false",
                t.scam_typology or "",
            ]
            for i, t in enumerate(w.txns, start=1)
        ],
    )

    personas = [
        {"customer_id": cid, **{k: v for k, v in p.items() if k != "balance"}}
        for cid, p in PERSONAS.items()
    ]
    (out / "personas.json").write_text(
        json.dumps(personas, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    scam_txns = sum(1 for t in w.txns if t.scam_typology)
    return {
        "customers": len(w.customers),
        "payees": len(w.payees),
        "transactions": len(w.txns),
        "scam_transactions": scam_txns,
        "scam_customers": len({t.customer_id for t in w.txns if t.scam_typology}),
    }


def main(argv: list[str] | None = None) -> dict[str, int]:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--customers", type=int, default=500)
    ap.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=datetime.now(SGT).date(),
        help="history ends at 00:00 SGT on this date (default: today)",
    )
    ap.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[1] / "seed")
    args = ap.parse_args(argv)
    if args.customers < len(PERSONAS):
        ap.error(f"--customers must be at least {len(PERSONAS)}")
    stats = write(build(args.seed, args.customers, args.end_date), args.out)
    print(json.dumps({"out": str(args.out), "end_date": args.end_date.isoformat(), **stats}))
    return stats


if __name__ == "__main__":
    main()
