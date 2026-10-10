"""make seed-local's two halves: CSV -> SQLite, and watchlist + personas -> StateRepo."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.data.memory_repo import MemoryStateRepo
from app.data.seed import load_sqlite, seed_state
from app.data.sqlite_repo import SqliteTransactionRepo


def test_sqlite_load_matches_the_csvs(seed_dir: Path, tmp_path: Path, csv_rows: dict) -> None:
    db = tmp_path / "x.db"
    counts = load_sqlite(db, seed_dir)
    assert counts == {t: len(rows) for t, rows in csv_rows.items()}
    with sqlite3.connect(db) as conn:
        labels = conn.execute("SELECT SUM(is_scam_label) FROM transactions").fetchone()[0]
        nulls = conn.execute("SELECT COUNT(*) FROM transactions WHERE payee_id IS NULL").fetchone()[
            0
        ]
    assert labels == sum(t["is_scam_label"] == "true" for t in csv_rows["transactions"])
    assert nulls == sum(t["payee_id"] == "" for t in csv_rows["transactions"])  # '' -> NULL
    assert SqliteTransactionRepo(db).ping()
    load_sqlite(db, seed_dir)  # re-seeding replaces the file atomically
    assert not db.with_suffix(".db.tmp").exists()


async def test_seed_state_is_idempotent_and_keeps_analyst_reports(seed_dir: Path) -> None:
    repo = MemoryStateRepo()
    first = await seed_state(repo, seed_dir)
    assert first == {"watchlist_replaced": 0, "watchlist": 30, "personas": 3}
    await repo.upsert_watchlist("DOMAIN", "mas-gov-verify.example", source="ANALYST_REPORT")
    again = await seed_state(repo, seed_dir)
    assert again == {"watchlist_replaced": 30, "watchlist": 30, "personas": 3}
    assert len(await repo.list_watchlist()) == 31
    assert await repo.get_watchlist("DOMAIN", "mas-gov-verify.example") is not None

    scammer = await repo.get_watchlist("PHONE", "+65 8000 0147")  # how Gemini might print it
    mule = await repo.get_watchlist("ACCOUNT", "123456789")
    assert scammer and mule and scammer.source == mule.source == "SEED"
    assert [p.full_name for p in await repo.list_personas()] == [
        "Tan Mei Ling",
        "Raj Kumar",
        "Nur Aisyah",
    ]
