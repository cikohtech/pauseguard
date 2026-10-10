# Phase 01: Synthetic data & data layer

**Read first:** `docs/DATA_SPEC.md` §1–3, `docs/ARCHITECTURE.md` (D6).

## Goal
Realistic synthetic bank data, available through one repository interface backed by SQLite (local) or BigQuery (cloud), plus seeded Firestore data.

## Tasks
1. `data/generate/make_synthetic.py` (seeded, deterministic): 500 customers, accounts, payees and 12 months of transactions, with scam episodes injected exactly as described in DATA_SPEC §2. It must include the 4 demo personas with their exact IDs and stories.
2. `data/seed/watchlist.json` (about 30 fake entries, including the cust_001 scenario's scammer phone number and account).
3. `backend/app/data/base.py` (the `TransactionRepo` protocol: `get_customer`, `get_payee_by_account`, `customer_history(customer_id, days)`, `recent_new_payee_transfers(customer_id, hours)`, `balance`), plus `sqlite_repo.py` and `bigquery_repo.py`, chosen by `DATA_BACKEND`.
4. `firestore_repo.py`: CRUD for checks, cases, audit, watchlist and feedback (it works against the emulator).
5. `infra/bq/*.json` schemas, `make seed-local` (CSV → SQLite + emulator) and `make seed-cloud` (CSV → BigQuery in asia-southeast1 + Firestore).
6. Tests: the generator is deterministic, the personas exist, and both repos return identical results for the same queries (the BigQuery test is marked `live`).

## Acceptance
`make seed-local` works from scratch in under 1 minute, and a quick script prints Mrs Tan's 90-day history. PROGRESS.md updated; commit `phase-01: synthetic data + repos`.
