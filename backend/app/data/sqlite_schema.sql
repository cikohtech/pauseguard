-- Local mirror of the BigQuery dataset `pauseguard` (DATA_SPEC §1; infra/bq/*.json).
-- Column names are identical in both backends. Timestamps are UTC text in one fixed format,
-- 'YYYY-MM-DD HH:MM:SS+00:00', so text comparison is time comparison. Booleans are 0/1.

CREATE TABLE IF NOT EXISTS customers (
  customer_id           TEXT PRIMARY KEY,
  full_name             TEXT NOT NULL,
  age                   INTEGER NOT NULL,
  preferred_language    TEXT NOT NULL,
  segment               TEXT NOT NULL,
  trusted_contact_name  TEXT,
  trusted_contact_phone TEXT,
  created_at            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS accounts (
  account_id  TEXT PRIMARY KEY,
  customer_id TEXT NOT NULL REFERENCES customers (customer_id),
  balance     REAL NOT NULL,
  currency    TEXT NOT NULL,
  opened_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS payees (
  payee_id       TEXT PRIMARY KEY,
  customer_id    TEXT NOT NULL REFERENCES customers (customer_id),
  payee_name     TEXT NOT NULL,
  account_number TEXT NOT NULL,
  bank_name      TEXT NOT NULL,
  country        TEXT NOT NULL,
  dest_type      TEXT NOT NULL,
  first_paid_at  TEXT,
  created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
  txn_id              TEXT PRIMARY KEY,
  customer_id         TEXT NOT NULL REFERENCES customers (customer_id),
  account_id          TEXT NOT NULL REFERENCES accounts (account_id),
  payee_id            TEXT REFERENCES payees (payee_id),
  amount              REAL NOT NULL,
  currency            TEXT NOT NULL,
  direction           TEXT NOT NULL,
  category            TEXT NOT NULL,
  ts                  TEXT NOT NULL,
  is_scam_label       INTEGER NOT NULL,  -- ground truth for analytics only
  scam_typology_label TEXT
);

-- Streamed by the API (phase 05) for the dashboard and the benchmark.
CREATE TABLE IF NOT EXISTS checks_analytics (
  check_id         TEXT PRIMARY KEY,
  ts               TEXT NOT NULL,
  customer_id      TEXT NOT NULL,
  amount           REAL,
  txn_score        INTEGER,
  verdict          TEXT,
  typology         TEXT,
  confidence       REAL,
  latency_ms       INTEGER,
  tokens_in        INTEGER,
  tokens_out       INTEGER,
  model            TEXT,
  analyst_decision TEXT,
  is_eval          INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_txn_customer_ts ON transactions (customer_id, ts);
CREATE INDEX IF NOT EXISTS idx_payees_customer ON payees (customer_id);
CREATE INDEX IF NOT EXISTS idx_accounts_customer ON accounts (customer_id);
