"""TransactionRepo + AnalyticsRepo on SQLite (DATA_BACKEND=sqlite, local dev).

Seeded by `make seed-local`. Semantics are defined in base.py; bigquery_repo.py runs the same
queries in BigQuery SQL. A connection is opened per call (read-only for bank data): it is cheap
for SQLite and safe across threads.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.data.base import HISTORY_DAYS, VELOCITY_HOURS, as_utc, window_start
from app.data.normalise import normalise_account
from app.log import get_logger
from app.models.schemas import BankTransaction, CheckAnalyticsRow, Customer, Payee, RiskSnapshot

SCHEMA_PATH = Path(__file__).with_name("sqlite_schema.sql")
TS_FORMAT = "%Y-%m-%d %H:%M:%S+00:00"  # the stored format; text order == time order
RECORDED_FORMAT = "%Y-%m-%d %H:%M:%S.%f+00:00"  # analytics snapshots: same order, microseconds
ANALYTICS_COLUMNS = list(CheckAnalyticsRow.model_fields)

# Same normalisation as normalise_account() for stored values (digits, dashes, spaces).
NORM_ACCOUNT_SQL = "UPPER(REPLACE(REPLACE(account_number, '-', ''), ' ', ''))"
TXN_COLUMNS = "txn_id, customer_id, account_id, payee_id, amount, currency, direction, category, ts"


def to_db_ts(dt: datetime) -> str:
    return as_utc(dt).strftime(TS_FORMAT)


class SqliteTransactionRepo:
    backend = "sqlite"

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        if not self.path.exists():
            raise FileNotFoundError(f"{self.path} not found: run `make seed-local` first.")
        conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _all(self, sql: str, params: dict[str, Any]) -> list[sqlite3.Row]:
        with self._conn() as conn:
            return conn.execute(sql, params).fetchall()

    def get_customer(self, customer_id: str) -> Customer | None:
        rows = self._all("SELECT * FROM customers WHERE customer_id = :cid", {"cid": customer_id})
        return Customer.model_validate(dict(rows[0])) if rows else None

    def get_payee_by_account(self, customer_id: str, account_number: str) -> Payee | None:
        rows = self._all(
            f"SELECT * FROM payees WHERE customer_id = :cid AND {NORM_ACCOUNT_SQL} = :acct "
            "ORDER BY first_paid_at IS NULL, first_paid_at, payee_id LIMIT 1",
            {"cid": customer_id, "acct": normalise_account(account_number)},
        )
        return Payee.model_validate(dict(rows[0])) if rows else None

    def customer_history(
        self, customer_id: str, days: int = HISTORY_DAYS, *, as_of: datetime | None = None
    ) -> list[BankTransaction]:
        end = as_utc(as_of)
        rows = self._all(
            f"SELECT {TXN_COLUMNS} FROM transactions "
            "WHERE customer_id = :cid AND ts >= :since AND ts < :as_of ORDER BY ts, txn_id",
            {
                "cid": customer_id,
                "since": to_db_ts(window_start(end, days=days)),
                "as_of": to_db_ts(end),
            },
        )
        return [BankTransaction.model_validate(dict(r)) for r in rows]

    def recent_new_payee_transfers(
        self, customer_id: str, hours: int = VELOCITY_HOURS, *, as_of: datetime | None = None
    ) -> list[BankTransaction]:
        end = as_utc(as_of)
        cols = ", ".join(f"t.{c.strip()}" for c in TXN_COLUMNS.split(","))
        rows = self._all(
            f"SELECT {cols} FROM transactions t JOIN payees p ON p.payee_id = t.payee_id "
            "WHERE t.customer_id = :cid AND t.direction = 'DEBIT' "
            "AND t.ts >= :since AND t.ts < :as_of "
            "AND p.first_paid_at >= :since AND p.first_paid_at < :as_of "
            "ORDER BY t.ts, t.txn_id",
            {
                "cid": customer_id,
                "since": to_db_ts(window_start(end, hours=hours)),
                "as_of": to_db_ts(end),
            },
        )
        return [BankTransaction.model_validate(dict(r)) for r in rows]

    def balance(self, customer_id: str) -> float | None:
        rows = self._all(
            "SELECT SUM(balance) AS b FROM accounts WHERE customer_id = :cid", {"cid": customer_id}
        )
        return None if rows[0]["b"] is None else round(float(rows[0]["b"]), 2)

    def risk_snapshot(
        self, customer_id: str, account_number: str, *, as_of: datetime | None = None
    ) -> RiskSnapshot:
        end = as_utc(as_of)
        sql = f"""
        WITH debits AS (
          SELECT amount, ROW_NUMBER() OVER (ORDER BY amount) AS rn, COUNT(*) OVER () AS n
          FROM transactions
          WHERE customer_id = :cid AND direction = 'DEBIT' AND ts >= :since_days AND ts < :as_of
        )
        SELECT
          (SELECT age FROM customers WHERE customer_id = :cid) AS customer_age,
          (SELECT SUM(balance) FROM accounts WHERE customer_id = :cid) AS balance,
          (SELECT COUNT(*) FROM payees
            WHERE customer_id = :cid AND {NORM_ACCOUNT_SQL} = :acct
              AND first_paid_at IS NOT NULL AND first_paid_at < :as_of) AS known_payees,
          (SELECT AVG(amount) FROM debits WHERE rn IN ((n + 1) / 2, (n + 2) / 2)) AS median_debit,
          (SELECT COUNT(*) FROM debits) AS debit_count,
          (SELECT COUNT(*) FROM transactions t JOIN payees p ON p.payee_id = t.payee_id
            WHERE t.customer_id = :cid AND t.direction = 'DEBIT'
              AND t.ts >= :since_hours AND t.ts < :as_of
              AND p.first_paid_at >= :since_hours AND p.first_paid_at < :as_of) AS new_payee_24h
        """
        (row,) = self._all(
            sql,
            {
                "cid": customer_id,
                "acct": normalise_account(account_number),
                "as_of": to_db_ts(end),
                "since_days": to_db_ts(window_start(end, days=HISTORY_DAYS)),
                "since_hours": to_db_ts(window_start(end, hours=VELOCITY_HOURS)),
            },
        )
        return RiskSnapshot(
            customer_id=customer_id,
            customer_age=row["customer_age"],
            balance=None if row["balance"] is None else round(float(row["balance"]), 2),
            payee_known=row["known_payees"] > 0,
            median_debit_90d=(
                None if row["median_debit"] is None else round(float(row["median_debit"]), 2)
            ),
            debit_count_90d=row["debit_count"],
            transfers_to_new_payees_24h=row["new_payee_24h"],
        )

    def ping(self) -> bool:
        try:
            self._all("SELECT 1 FROM customers LIMIT 1", {})
        except (FileNotFoundError, sqlite3.Error):
            return False
        return True


class SqliteAnalyticsRepo:
    """`checks_analytics` in the local database. A database built before phase 05 has the old
    table (check_id as primary key, no recorded_at); it is rebuilt on first use (dev data only).
    """

    backend = "sqlite"

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._ready = False

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        if not self.path.exists():
            raise FileNotFoundError(f"{self.path} not found: run `make seed-local` first.")
        conn = sqlite3.connect(self.path, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            if not self._ready:
                cols = {r["name"] for r in conn.execute("PRAGMA table_info(checks_analytics)")}
                if "recorded_at" not in cols:
                    get_logger(__name__).warning("checks_analytics_rebuilt", path=str(self.path))
                    conn.execute("DROP TABLE IF EXISTS checks_analytics")
                    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
                self._ready = True
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, rows: Sequence[CheckAnalyticsRow]) -> None:
        marks = ", ".join(f":{c}" for c in ANALYTICS_COLUMNS)
        values = []
        for r in rows:
            d = r.model_dump()
            d["ts"] = to_db_ts(r.ts)
            d["recorded_at"] = as_utc_exact(r.recorded_at).strftime(RECORDED_FORMAT)
            d["fast_path"], d["is_eval"] = int(r.fast_path), int(r.is_eval)
            values.append(d)
        with self._conn() as conn:
            conn.executemany(
                f"INSERT INTO checks_analytics ({', '.join(ANALYTICS_COLUMNS)}) VALUES ({marks})",
                values,
            )

    def latest_rows(
        self, since: datetime, *, include_eval: bool = False
    ) -> list[CheckAnalyticsRow]:
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT {", ".join(ANALYTICS_COLUMNS)} FROM (
                  SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY check_id ORDER BY recorded_at DESC, rowid DESC) AS rn
                  FROM checks_analytics WHERE ts >= :since AND (:include_eval OR is_eval = 0)
                ) WHERE rn = 1 ORDER BY ts, check_id
                """,
                {"since": to_db_ts(since), "include_eval": int(include_eval)},
            ).fetchall()
        return [CheckAnalyticsRow.model_validate(dict(r)) for r in rows]


def as_utc_exact(dt: datetime) -> datetime:
    """Like as_utc, but keeps the microseconds (snapshot order within one second)."""
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)
