"""TransactionRepo: SQLite against a brute-force reference of the base.py semantics, and
BigQuery against SQLite on the same CSVs (`-m live`, needs a GCP project)."""

from __future__ import annotations

import secrets
import statistics
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from app.config import Settings
from app.data import get_transaction_repo
from app.data.base import TransactionRepo
from app.data.normalise import normalise_account
from app.data.sqlite_repo import SqliteTransactionRepo
from app.models.schemas import BankTransaction, RiskSnapshot
from tests.conftest import AS_OF

Rows = dict[str, list[dict[str, str]]]


def ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def expected_snapshot(rows: Rows, cid: str, account: str, as_of: datetime) -> RiskSnapshot:
    """base.py semantics, written out in plain Python over the CSVs."""
    cust = next((c for c in rows["customers"] if c["customer_id"] == cid), None)
    accounts = [float(a["balance"]) for a in rows["accounts"] if a["customer_id"] == cid]
    payees = {p["payee_id"]: p for p in rows["payees"]}
    known = any(
        p["customer_id"] == cid
        and normalise_account(p["account_number"]) == normalise_account(account)
        and p["first_paid_at"]
        and ts(p["first_paid_at"]) < as_of
        for p in rows["payees"]
    )
    mine = [t for t in rows["transactions"] if t["customer_id"] == cid]
    debits = [
        float(t["amount"])
        for t in mine
        if t["direction"] == "DEBIT" and as_of - timedelta(days=90) <= ts(t["ts"]) < as_of
    ]
    since = as_of - timedelta(hours=24)
    velocity = [
        t
        for t in mine
        if t["direction"] == "DEBIT"
        and t["payee_id"]
        and since <= ts(t["ts"]) < as_of
        and payees[t["payee_id"]]["first_paid_at"]
        and since <= ts(payees[t["payee_id"]]["first_paid_at"]) < as_of
    ]
    return RiskSnapshot(
        customer_id=cid,
        customer_age=int(cust["age"]) if cust else None,
        balance=round(sum(accounts), 2) if accounts else None,
        payee_known=known,
        median_debit_90d=round(statistics.median(debits), 2) if debits else None,
        debit_count_90d=len(debits),
        transfers_to_new_payees_24h=len(velocity),
    )


def scam_bursts(rows: Rows, typology: str) -> list[list[dict[str, str]]]:
    by_cust: dict[str, list[dict[str, str]]] = {}
    for t in rows["transactions"]:
        if t["scam_typology_label"] == typology:
            by_cust.setdefault(t["customer_id"], []).append(t)
    return list(by_cust.values())


def probe_points(rows: Rows) -> list[tuple[str, str, datetime]]:
    """(customer, account, as_of) triples that exercise every branch of the snapshot."""
    payees = {p["payee_id"]: p for p in rows["payees"]}
    points = [
        ("cust_001", "123-45678-9", AS_OF),  # Mrs Tan's demo transfer: unknown payee
        ("cust_002", "999-99999-9", AS_OF),
        ("cust_003", "999-99999-9", AS_OF),
        ("cust_999", "1", AS_OF),  # no such customer
    ]
    tan_bill = next(p for p in rows["payees"] if p["customer_id"] == "cust_001")
    points.append(("cust_001", tan_bill["account_number"].replace("-", " "), AS_OF))
    for typology in ("JOB_TASK", "GOV_OFFICIAL_IMPERSONATION", "INVESTMENT"):
        for burst in scam_bursts(rows, typology):
            last = burst[-1]
            after = ts(last["ts"]) + timedelta(seconds=1)
            acct = payees[last["payee_id"]]["account_number"]
            points += [
                (last["customer_id"], acct, after),
                (last["customer_id"], acct, ts(last["ts"])),
            ]
    return points


def test_get_customer(sqlite_repo: SqliteTransactionRepo) -> None:
    tan = sqlite_repo.get_customer("cust_001")
    assert tan is not None
    assert (tan.full_name, tan.age, tan.preferred_language, tan.segment) == (
        "Tan Mei Ling",
        67,
        "zh",
        "RETIREE",
    )
    assert tan.trusted_contact_phone == "+65 8000 0300"
    assert sqlite_repo.get_customer("cust_004") is None
    assert sqlite_repo.balance("cust_001") == 42180.55
    assert sqlite_repo.balance("cust_999") is None


def test_get_payee_by_account_ignores_formatting(
    sqlite_repo: SqliteTransactionRepo, csv_rows: Rows
) -> None:
    landlord = next(
        p
        for p in csv_rows["payees"]
        if p["customer_id"] == "cust_003" and p["payee_name"] == "Koh Residences Pte Ltd"
    )
    digits = normalise_account(landlord["account_number"])
    for variant in (
        landlord["account_number"],
        digits,
        " ".join(digits),
        f" {digits[:3]}.{digits[3:]} ",
    ):
        found = sqlite_repo.get_payee_by_account("cust_003", variant)
        assert found is not None and found.payee_id == landlord["payee_id"], variant
    assert sqlite_repo.get_payee_by_account("cust_001", landlord["account_number"]) is None
    assert sqlite_repo.get_payee_by_account("cust_001", "123-45678-9") is None


def test_customer_history_window(sqlite_repo: SqliteTransactionRepo, csv_rows: Rows) -> None:
    hist = sqlite_repo.customer_history("cust_001", 90, as_of=AS_OF)
    expected = [
        t["txn_id"]
        for t in csv_rows["transactions"]
        if t["customer_id"] == "cust_001" and AS_OF - timedelta(days=90) <= ts(t["ts"]) < AS_OF
    ]
    assert [t.txn_id for t in hist] == expected
    assert 10 <= len(hist) <= 20  # four bills and one payout a month
    assert [t.ts for t in hist] == sorted(t.ts for t in hist)
    assert all(t.ts.utcoffset() == timedelta(0) for t in hist)
    assert len(sqlite_repo.customer_history("cust_001", 365, as_of=AS_OF)) > len(hist)
    assert sqlite_repo.customer_history("cust_001", 90, as_of=AS_OF - timedelta(days=400)) == []


def test_ground_truth_is_never_exposed() -> None:
    assert not {"is_scam_label", "scam_typology_label"} & set(BankTransaction.model_fields)
    assert not {"is_scam_label", "scam_typology_label"} & set(RiskSnapshot.model_fields)


def test_recent_new_payee_transfers_catch_a_job_scam(
    sqlite_repo: SqliteTransactionRepo, csv_rows: Rows
) -> None:
    burst = max(scam_bursts(csv_rows, "JOB_TASK"), key=len)
    cid, after = burst[-1]["customer_id"], ts(burst[-1]["ts"]) + timedelta(seconds=1)
    got = sqlite_repo.recent_new_payee_transfers(cid, 24, as_of=after)
    in_window = [t["txn_id"] for t in burst if after - timedelta(hours=24) <= ts(t["ts"]) < after]
    assert [t.txn_id for t in got] == in_window
    assert len(got) >= 2
    assert sqlite_repo.recent_new_payee_transfers(cid, 24, as_of=after + timedelta(days=30)) == []


def test_risk_snapshot_matches_reference(
    sqlite_repo: SqliteTransactionRepo, csv_rows: Rows
) -> None:
    for cid, acct, as_of in probe_points(csv_rows):
        assert sqlite_repo.risk_snapshot(cid, acct, as_of=as_of) == expected_snapshot(
            csv_rows, cid, acct, as_of
        ), (cid, acct, as_of)


def test_risk_snapshot_for_the_demo_personas(sqlite_repo: SqliteTransactionRepo) -> None:
    tan = sqlite_repo.risk_snapshot("cust_001", "123-45678-9", as_of=AS_OF)
    assert not tan.payee_known and tan.customer_age == 67
    assert tan.median_debit_90d is not None and 8000 / tan.median_debit_90d >= 10  # +30 spike
    assert tan.transfers_to_new_payees_24h == 0
    raj = sqlite_repo.risk_snapshot("cust_002", "777-12345-6", as_of=AS_OF)
    assert raj.median_debit_90d is not None and 450 / raj.median_debit_90d >= 3
    aisyah = sqlite_repo.risk_snapshot("cust_003", "555-00000-1", as_of=AS_OF)
    assert not aisyah.payee_known and aisyah.balance and 3200 / aisyah.balance < 0.5


def test_missing_database_is_reported(tmp_path: Path) -> None:
    repo = SqliteTransactionRepo(tmp_path / "nope.db")
    assert repo.ping() is False
    with pytest.raises(FileNotFoundError, match="make seed-local"):
        repo.get_customer("cust_001")


def test_factory_picks_the_backend(tmp_path: Path) -> None:
    sqlite = get_transaction_repo(
        Settings(data_backend="sqlite", sqlite_path=tmp_path / "x.db", _env_file=None)
    )
    assert isinstance(sqlite, TransactionRepo) and sqlite.backend == "sqlite"
    bq = get_transaction_repo(
        Settings(data_backend="bigquery", google_cloud_project="p", _env_file=None)
    )
    assert isinstance(bq, TransactionRepo) and bq.backend == "bigquery"


@pytest.mark.live
def test_bigquery_returns_what_sqlite_returns(
    seed_dir: Path, sqlite_repo: SqliteTransactionRepo, csv_rows: Rows
) -> None:
    """Loads the same CSVs into a throwaway dataset, runs every query on both, then drops it."""
    from google.cloud import bigquery

    from app.config import get_settings
    from app.data.bigquery_repo import BigQueryTransactionRepo
    from app.data.seed import load_bigquery

    settings = get_settings()
    if settings.google_cloud_project in ("", "your-project-id"):
        pytest.skip("GOOGLE_CLOUD_PROJECT is not set")
    client = bigquery.Client(project=settings.google_cloud_project, location=settings.data_region)
    dataset = f"pauseguard_parity_{secrets.token_hex(4)}"
    try:
        load_bigquery(client, dataset, settings.data_region, seed_dir)
        bq = BigQueryTransactionRepo(client.project, dataset, settings.data_region, client)
        assert bq.ping()
        for cid in ("cust_001", "cust_002", "cust_003", "cust_999"):
            assert bq.get_customer(cid) == sqlite_repo.get_customer(cid)
            assert bq.balance(cid) == sqlite_repo.balance(cid)
            assert bq.customer_history(cid, 90, as_of=AS_OF) == sqlite_repo.customer_history(
                cid, 90, as_of=AS_OF
            )
        for cid, acct, as_of in probe_points(csv_rows):
            assert bq.get_payee_by_account(cid, acct) == sqlite_repo.get_payee_by_account(cid, acct)
            assert bq.recent_new_payee_transfers(cid, 24, as_of=as_of) == (
                sqlite_repo.recent_new_payee_transfers(cid, 24, as_of=as_of)
            )
            b, s = (
                bq.risk_snapshot(cid, acct, as_of=as_of),
                sqlite_repo.risk_snapshot(cid, acct, as_of=as_of),
            )
            assert b.model_dump(exclude={"median_debit_90d"}) == s.model_dump(
                exclude={"median_debit_90d"}
            )
            if s.median_debit_90d is None:
                assert b.median_debit_90d is None
            else:
                assert b.median_debit_90d == pytest.approx(s.median_debit_90d, abs=0.006)
    finally:
        client.delete_dataset(
            f"{client.project}.{dataset}", delete_contents=True, not_found_ok=True
        )


def test_bigquery_parameter_types_accept_datetime_subclasses() -> None:
    from google.api_core.datetime_helpers import DatetimeWithNanoseconds

    from app.data.bigquery_repo import param_type

    firestore_ts = DatetimeWithNanoseconds(2026, 10, 11, 6, 0, tzinfo=UTC)  # a check's created_at
    assert param_type(firestore_ts) == "TIMESTAMP"
    assert param_type(datetime(2026, 10, 11, tzinfo=UTC)) == "TIMESTAMP"
    assert (param_type(True), param_type(3), param_type("cust_001")) == ("BOOL", "INT64", "STRING")
    with pytest.raises(TypeError):
        param_type(1.5)
