"""TransactionRepo + AnalyticsRepo on BigQuery (DATA_BACKEND=bigquery, cloud).

Seeded by `make seed-cloud`. Analytics rows are streamed in (`insert_rows_json`).

Same semantics as sqlite_repo.py (see base.py); the parity test (`-m live`) runs the same
queries on both and compares the results. Every query is parameterised.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from google.cloud import bigquery

from app.data.base import HISTORY_DAYS, VELOCITY_HOURS, as_utc, window_start
from app.data.normalise import normalise_account
from app.models.schemas import BankTransaction, CheckAnalyticsRow, Customer, Payee, RiskSnapshot

NORM_ACCOUNT_SQL = "UPPER(REPLACE(REPLACE(account_number, '-', ''), ' ', ''))"
TXN_COLUMNS = [
    "txn_id",
    "customer_id",
    "account_id",
    "payee_id",
    "amount",
    "currency",
    "direction",
    "category",
    "ts",
]


def _num(v: Decimal | float | None) -> float | None:
    return None if v is None else round(float(v), 2)


def param_type(value: Any) -> str:
    """The BigQuery type of a query parameter. isinstance, not type(): a timestamp read back from
    Firestore is a `datetime` subclass (DatetimeWithNanoseconds), and bool is checked before int
    because bool is an int."""
    for py, bq in ((bool, "BOOL"), (int, "INT64"), (str, "STRING"), (datetime, "TIMESTAMP")):
        if isinstance(value, py):
            return bq
    raise TypeError(f"No BigQuery parameter type for {type(value).__name__}")


class BigQueryTransactionRepo:
    backend = "bigquery"

    def __init__(
        self,
        project: str,
        dataset: str,
        location: str = "asia-southeast1",
        client: bigquery.Client | None = None,
    ) -> None:
        self.project, self.dataset, self.location = project, dataset, location
        self._client = client

    @property
    def client(self) -> bigquery.Client:
        if self._client is None:
            self._client = bigquery.Client(project=self.project, location=self.location)
        return self._client

    def _t(self, table: str) -> str:
        return f"`{self.project}.{self.dataset}.{table}`"

    def _rows(self, sql: str, **params: Any) -> list[bigquery.Row]:
        config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(k, param_type(v), v) for k, v in params.items()
            ]
        )
        return list(self.client.query(sql, job_config=config, location=self.location).result())

    @staticmethod
    def _txn(row: bigquery.Row) -> BankTransaction:
        d = dict(row.items())
        d["amount"] = _num(d["amount"])
        return BankTransaction.model_validate(d)

    def get_customer(self, customer_id: str) -> Customer | None:
        rows = self._rows(
            f"SELECT * FROM {self._t('customers')} WHERE customer_id = @cid", cid=customer_id
        )
        return Customer.model_validate(dict(rows[0].items())) if rows else None

    def get_payee_by_account(self, customer_id: str, account_number: str) -> Payee | None:
        rows = self._rows(
            f"SELECT * FROM {self._t('payees')} "
            f"WHERE customer_id = @cid AND {NORM_ACCOUNT_SQL} = @acct "
            "ORDER BY first_paid_at IS NULL, first_paid_at, payee_id LIMIT 1",
            cid=customer_id,
            acct=normalise_account(account_number),
        )
        return Payee.model_validate(dict(rows[0].items())) if rows else None

    def customer_history(
        self, customer_id: str, days: int = HISTORY_DAYS, *, as_of: datetime | None = None
    ) -> list[BankTransaction]:
        end = as_utc(as_of)
        rows = self._rows(
            f"SELECT {', '.join(TXN_COLUMNS)} FROM {self._t('transactions')} "
            "WHERE customer_id = @cid AND ts >= @since AND ts < @as_of ORDER BY ts, txn_id",
            cid=customer_id,
            since=window_start(end, days=days),
            as_of=end,
        )
        return [self._txn(r) for r in rows]

    def recent_new_payee_transfers(
        self, customer_id: str, hours: int = VELOCITY_HOURS, *, as_of: datetime | None = None
    ) -> list[BankTransaction]:
        end = as_utc(as_of)
        rows = self._rows(
            f"SELECT {', '.join('t.' + c for c in TXN_COLUMNS)} "
            f"FROM {self._t('transactions')} t JOIN {self._t('payees')} p "
            "ON p.payee_id = t.payee_id "
            "WHERE t.customer_id = @cid AND t.direction = 'DEBIT' "
            "AND t.ts >= @since AND t.ts < @as_of "
            "AND p.first_paid_at >= @since AND p.first_paid_at < @as_of "
            "ORDER BY t.ts, t.txn_id",
            cid=customer_id,
            since=window_start(end, hours=hours),
            as_of=end,
        )
        return [self._txn(r) for r in rows]

    def balance(self, customer_id: str) -> float | None:
        rows = self._rows(
            f"SELECT SUM(balance) AS b FROM {self._t('accounts')} WHERE customer_id = @cid",
            cid=customer_id,
        )
        return _num(rows[0]["b"])

    def risk_snapshot(
        self, customer_id: str, account_number: str, *, as_of: datetime | None = None
    ) -> RiskSnapshot:
        end = as_utc(as_of)
        sql = f"""
        WITH debits AS (
          SELECT amount FROM {self._t("transactions")}
          WHERE customer_id = @cid AND direction = 'DEBIT' AND ts >= @since_days AND ts < @as_of
        )
        SELECT
          (SELECT age FROM {self._t("customers")} WHERE customer_id = @cid) AS customer_age,
          (SELECT SUM(balance) FROM {self._t("accounts")} WHERE customer_id = @cid) AS balance,
          (SELECT COUNT(*) FROM {self._t("payees")}
            WHERE customer_id = @cid AND {NORM_ACCOUNT_SQL} = @acct
              AND first_paid_at IS NOT NULL AND first_paid_at < @as_of) AS known_payees,
          (SELECT ANY_VALUE(m) FROM (SELECT PERCENTILE_CONT(amount, 0.5) OVER () AS m
                                     FROM debits)) AS median_debit,
          (SELECT COUNT(*) FROM debits) AS debit_count,
          (SELECT COUNT(*) FROM {self._t("transactions")} t
            JOIN {self._t("payees")} p ON p.payee_id = t.payee_id
            WHERE t.customer_id = @cid AND t.direction = 'DEBIT'
              AND t.ts >= @since_hours AND t.ts < @as_of
              AND p.first_paid_at >= @since_hours AND p.first_paid_at < @as_of) AS new_payee_24h
        """
        (row,) = self._rows(
            sql,
            cid=customer_id,
            acct=normalise_account(account_number),
            as_of=end,
            since_days=window_start(end, days=HISTORY_DAYS),
            since_hours=window_start(end, hours=VELOCITY_HOURS),
        )
        return RiskSnapshot(
            customer_id=customer_id,
            customer_age=row["customer_age"],
            balance=_num(row["balance"]),
            payee_known=row["known_payees"] > 0,
            median_debit_90d=_num(row["median_debit"]),
            debit_count_90d=row["debit_count"],
            transfers_to_new_payees_24h=row["new_payee_24h"],
        )

    def ping(self) -> bool:
        try:
            self._rows(f"SELECT 1 FROM {self._t('customers')} LIMIT 1")
        except Exception:  # any failure means "not healthy"
            return False
        return True


class BigQueryAnalyticsRepo(BigQueryTransactionRepo):
    """`checks_analytics` (created by `make seed-cloud`, partitioned by day on ts). Shares the
    client and query helper with the transaction repo."""

    backend = "bigquery"

    def record(self, rows: Sequence[CheckAnalyticsRow]) -> None:
        table = f"{self.project}.{self.dataset}.checks_analytics"
        payload = [r.model_dump(mode="json") for r in rows]
        # The insert ID makes a retried insert of the same snapshot a no-op (best effort).
        ids = [f"{r.check_id}:{r.recorded_at.isoformat()}" for r in rows]
        errors = self.client.insert_rows_json(table, payload, row_ids=ids)
        if errors:
            raise RuntimeError(f"checks_analytics insert failed: {errors}")

    def latest_rows(
        self, since: datetime, *, include_eval: bool = False
    ) -> list[CheckAnalyticsRow]:
        rows = self._rows(
            f"SELECT * EXCEPT (rn) FROM ("
            f"  SELECT *, ROW_NUMBER() OVER ("
            f"    PARTITION BY check_id ORDER BY recorded_at DESC) AS rn"
            f"  FROM {self._t('checks_analytics')}"
            f"  WHERE ts >= @since AND (@include_eval OR NOT is_eval)"
            f") WHERE rn = 1 ORDER BY ts, check_id",
            since=as_utc(since),
            include_eval=include_eval,
        )
        out = []
        for row in rows:
            d = dict(row.items())
            d["amount"] = _num(d["amount"])
            d["fast_path"] = bool(d.get("fast_path"))
            out.append(CheckAnalyticsRow.model_validate(d))
        return out
