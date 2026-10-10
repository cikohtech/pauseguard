"""Shared fixtures: one synthetic dataset (fixed seed and end date) and its SQLite database."""

from __future__ import annotations

import csv
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest

from app.data.seed import generate, load_sqlite
from app.data.sqlite_repo import SqliteTransactionRepo

SGT = timezone(timedelta(hours=8))
END_DATE = date(2026, 10, 10)
AS_OF = datetime.combine(END_DATE, time(0), SGT)  # the end of the generated history
SEED = 42


@pytest.fixture(scope="session")
def seed_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("seed")
    generate(SEED, END_DATE, out)
    (out / "watchlist.json").write_text(
        (Path(__file__).resolve().parents[2] / "data" / "seed" / "watchlist.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    return out


@pytest.fixture(scope="session")
def csv_rows(seed_dir: Path) -> dict[str, list[dict[str, str]]]:
    tables = ("customers", "accounts", "payees", "transactions")
    return {t: list(csv.DictReader((seed_dir / f"{t}.csv").open(encoding="utf-8"))) for t in tables}


@pytest.fixture(scope="session")
def sqlite_repo(seed_dir: Path) -> SqliteTransactionRepo:
    db = seed_dir / "pauseguard.db"
    load_sqlite(db, seed_dir)
    return SqliteTransactionRepo(db)
