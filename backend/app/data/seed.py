"""Seed the data stores from data/seed/ (DATA_SPEC §1-3).

    python -m app.data.seed local          # make seed-local: CSV -> SQLite (+ emulator)
    python -m app.data.seed cloud          # make seed-cloud: CSV -> BigQuery + Firestore
    python -m app.data.seed history [cust_001] [--days 90]   # make history

`local` and `cloud` first regenerate the CSVs (data/generate/make_synthetic.py; same seed,
history ending today), then load them. Firestore gets the watchlist (data/seed/watchlist.json,
source SEED) and the 3 demo personas; checks and cases are never touched here.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import importlib.util
import json
import os
import socket
import sqlite3
import sys
import time
from datetime import date, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import REPO_ROOT, Settings, get_settings
from app.data.base import StateRepo, utcnow
from app.models.schemas import Persona, WatchlistEntry

SEED_DIR = REPO_ROOT / "data" / "seed"
GENERATOR = REPO_ROOT / "data" / "generate" / "make_synthetic.py"
BQ_SCHEMA_DIR = REPO_ROOT / "infra" / "bq"
SQLITE_SCHEMA = Path(__file__).with_name("sqlite_schema.sql")
SGT = timezone(timedelta(hours=8))
TABLES = ["customers", "accounts", "payees", "transactions"]  # load order (foreign keys)


def generate(
    seed: int, end_date: date | None, out: Path = SEED_DIR, *, customers: int = 500
) -> dict[str, int]:
    spec = importlib.util.spec_from_file_location("make_synthetic", GENERATOR)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod  # dataclasses resolve annotations through sys.modules
    spec.loader.exec_module(mod)
    argv = ["--seed", str(seed), "--out", str(out), "--customers", str(customers)]
    if end_date:
        argv += ["--end-date", end_date.isoformat()]
    stats: dict[str, int] = mod.main(argv)
    return stats


def _csv_rows(table: str, seed_dir: Path) -> tuple[list[str], list[list[Any]]]:
    with (seed_dir / f"{table}.csv").open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows: list[list[Any]] = []
        for raw in reader:
            row: list[Any] = [v if v != "" else None for v in raw]
            if table == "transactions":
                row[header.index("is_scam_label")] = int(
                    raw[header.index("is_scam_label")] == "true"
                )
            rows.append(row)
    return header, rows


def load_sqlite(db_path: Path, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    """Build the database in a temp file, then swap it in, so readers never see half a load."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = db_path.with_suffix(".db.tmp")
    tmp.unlink(missing_ok=True)
    counts: dict[str, int] = {}
    conn = sqlite3.connect(tmp)
    try:
        conn.executescript(SQLITE_SCHEMA.read_text(encoding="utf-8"))
        for table in TABLES:
            header, rows = _csv_rows(table, seed_dir)
            marks = ", ".join("?" for _ in header)
            conn.executemany(f"INSERT INTO {table} ({', '.join(header)}) VALUES ({marks})", rows)
            counts[table] = len(rows)
        conn.commit()
    finally:
        conn.close()
    os.replace(tmp, db_path)
    return counts


def watchlist_entries(seed_dir: Path = SEED_DIR) -> list[WatchlistEntry]:
    data = json.loads((seed_dir / "watchlist.json").read_text(encoding="utf-8"))
    return [WatchlistEntry.model_validate({**e, "source": "SEED"}) for e in data["entries"]]


def personas(seed_dir: Path = SEED_DIR) -> list[Persona]:
    data = json.loads((seed_dir / "personas.json").read_text(encoding="utf-8"))
    return [Persona.model_validate(p) for p in data]


async def seed_state(repo: StateRepo, seed_dir: Path = SEED_DIR) -> dict[str, int]:
    """Replace the SEED watchlist entries and the personas. Analyst reports are kept."""
    removed = await repo.delete_watchlist(source="SEED")
    entries = watchlist_entries(seed_dir)
    for e in entries:
        await repo.put_watchlist(e)
    people = personas(seed_dir)
    for p in people:
        await repo.put_persona(p)
    return {"watchlist_replaced": removed, "watchlist": len(entries), "personas": len(people)}


def emulator_up(host_port: str) -> bool:
    host, _, port = host_port.rpartition(":")
    try:
        with socket.create_connection((host or "localhost", int(port)), timeout=0.5):
            return True
    except OSError:
        return False


def load_bigquery(
    client: Any, dataset_id: str, location: str, seed_dir: Path = SEED_DIR
) -> dict[str, int]:
    """CSV -> BigQuery tables (WRITE_TRUNCATE); checks_analytics is created, never truncated."""
    from google.cloud import bigquery

    project = client.project
    dataset = bigquery.Dataset(f"{project}.{dataset_id}")
    dataset.location = location
    client.create_dataset(dataset, exists_ok=True)
    counts: dict[str, int] = {}
    for table in TABLES:
        config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            skip_leading_rows=1,
            schema=client.schema_from_json(str(BQ_SCHEMA_DIR / f"{table}.json")),
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )
        if table == "transactions":
            config.time_partitioning = bigquery.TimePartitioning(field="ts")
            config.clustering_fields = ["customer_id"]
        with (seed_dir / f"{table}.csv").open("rb") as f:
            job = client.load_table_from_file(
                f, f"{project}.{dataset_id}.{table}", job_config=config
            )
        job.result()
        counts[table] = int(job.output_rows or 0)
    analytics = bigquery.Table(
        f"{project}.{dataset_id}.checks_analytics",
        schema=client.schema_from_json(str(BQ_SCHEMA_DIR / "checks_analytics.json")),
    )
    analytics.time_partitioning = bigquery.TimePartitioning(field="ts")
    client.create_table(analytics, exists_ok=True)  # holds real check history: keep it
    return counts


# --- commands ---------------------------------------------------------------------------------


def cmd_local(args: argparse.Namespace, settings: Settings) -> None:
    t0 = time.perf_counter()
    stats = generate(args.seed, args.end_date)
    counts = load_sqlite(settings.sqlite_path)
    print(f"✔ SQLite {settings.sqlite_path.relative_to(REPO_ROOT)}: {counts}")
    host = settings.firestore_emulator_host
    if host and emulator_up(host):
        from app.data.firestore_repo import FirestoreStateRepo

        settings.export_sdk_env()
        repo = FirestoreStateRepo(project=settings.firestore_project)
        print(f"✔ Firestore emulator {host}: {asyncio.run(seed_state(repo))}")
    else:
        print(f"ℹ Firestore emulator not reachable at {host}: skipped (start it: make emulators)")
    print(f"Done in {time.perf_counter() - t0:.1f}s; {stats['scam_customers']} scam episodes.")


def cmd_cloud(args: argparse.Namespace, settings: Settings) -> None:
    from google.cloud import bigquery

    from app.data.firestore_repo import FirestoreStateRepo

    project, region = settings.google_cloud_project, settings.data_region
    if project in ("", "your-project-id"):
        sys.exit("Set GOOGLE_CLOUD_PROJECT in .env first (see docs/DEPLOYMENT.md §1).")
    os.environ.pop("FIRESTORE_EMULATOR_HOST", None)  # this run must reach the real Firestore
    t0 = time.perf_counter()
    generate(args.seed, args.end_date)

    bq = bigquery.Client(project=project, location=region)
    for table, rows in load_bigquery(bq, settings.bq_dataset, region).items():
        print(f"✔ BigQuery {settings.bq_dataset}.{table}: {rows} rows")

    repo = FirestoreStateRepo(project=project)
    print(f"✔ Firestore ({project}): {asyncio.run(seed_state(repo))}")
    print(f"Done in {time.perf_counter() - t0:.1f}s.")


def cmd_history(args: argparse.Namespace, settings: Settings) -> None:
    from app.data import get_transaction_repo

    repo = get_transaction_repo(settings)
    customer = repo.get_customer(args.customer_id)
    if customer is None:
        sys.exit(f"{args.customer_id} not found ({repo.backend}); run make seed-local first.")
    txns = repo.customer_history(args.customer_id, args.days)
    balance = repo.balance(customer.customer_id) or 0.0
    print(f"{customer.full_name} ({customer.customer_id}), {customer.age}, ", end="")
    print(f"{customer.preferred_language}, {customer.segment}; balance S${balance:,.2f}")
    now = utcnow().astimezone(SGT)
    print(f"Last {args.days} days to {now:%Y-%m-%d %H:%M} SGT ({repo.backend}): {len(txns)} txns")
    for t in txns:
        sign = "-" if t.direction == "DEBIT" else "+"
        when = t.ts.astimezone(SGT)
        amount = f"{sign}S${t.amount:>9,.2f}"
        print(f"  {when:%Y-%m-%d %H:%M}  {amount}  {t.category:<10} {t.payee_id or ''}")
    snap = repo.risk_snapshot(args.customer_id, "123-45678-9")  # the demo's "safe account"
    print(f"Risk snapshot for a transfer to 123-45678-9: {snap.model_dump()}")


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="python -m app.data.seed", description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("local", "cloud"):
        p = sub.add_parser(name)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument(
            "--end-date",
            type=date.fromisoformat,
            default=None,
            help="last day of history, exclusive (default: today, SGT)",
        )
    h = sub.add_parser("history")
    h.add_argument("customer_id", nargs="?", default="cust_001")
    h.add_argument("--days", type=int, default=90)
    args = ap.parse_args(argv)
    settings = get_settings()
    {"local": cmd_local, "cloud": cmd_cloud, "history": cmd_history}[args.cmd](args, settings)


if __name__ == "__main__":
    main()
