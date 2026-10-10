# Data Spec: PauseGuard

All data is **synthetic**. Use the fictional bank "Harbour Bank". Don't use any real person, phone number, account number or real bank brand. Phone numbers use the reserved-looking pattern `+65 8000 0xxx`, and URLs use `.example` or obviously fake domains (for example `mas-gov-verify.example`).

## 1. Relational data (SQLite locally, BigQuery dataset `pauseguard` in cloud)

Keep the column names identical in both backends. DDL lives in `infra/bq/*.json` and `backend/app/data/sqlite_schema.sql`.

**customers**
| column | type | notes |
|---|---|---|
| customer_id | STRING | `cust_001`… |
| full_name | STRING | synthetic |
| age | INT64 | |
| preferred_language | STRING | en / zh / ms / ta |
| segment | STRING | RETIREE, STUDENT, WORKER, SME_OWNER |
| trusted_contact_name | STRING | nullable |
| trusted_contact_phone | STRING | nullable, synthetic |
| created_at | TIMESTAMP | |

**accounts**: `account_id, customer_id, balance, currency (SGD), opened_at`

**payees**: `payee_id, customer_id, payee_name, account_number, bank_name, country, dest_type (LOCAL_BANK|OVERSEAS|CRYPTO_EXCHANGE|MERCHANT|PAYNOW), first_paid_at (nullable), created_at`

**transactions**
| column | type |
|---|---|
| txn_id | STRING |
| customer_id | STRING |
| account_id | STRING |
| payee_id | STRING (nullable for card/merchant) |
| amount | NUMERIC |
| currency | STRING |
| direction | STRING (DEBIT/CREDIT) |
| category | STRING (SALARY, BILLS, GROCERIES, RENT, FAMILY, TRANSFER, SHOPPING, INVESTMENT) |
| ts | TIMESTAMP |
| is_scam_label | BOOL (ground truth for analytics only; never read by the risk tool) |
| scam_typology_label | STRING nullable |

**checks_analytics** (BigQuery only; streamed from the API for the dashboard and benchmark): `check_id, ts, customer_id, amount, txn_score, verdict, typology, confidence, latency_ms, tokens_in, tokens_out, model, analyst_decision (nullable), is_eval (bool)`

## 2. Generator (`data/generate/make_synthetic.py`)

- Seeded random (`--seed 42`), deterministic output.
- 500 customers: age distribution 18–85 (25% are 60+). Language mix: 55% en, 30% zh, 10% ms, 5% ta.
- 12 months of history per customer, about 50k–80k transactions in total: monthly salary credit, utilities, telco, rent, groceries, family transfers, some investments to legitimate brokers.
- Inject about 3% scam episodes following typology playbooks (for example, GOV impersonation: a new LOCAL_BANK payee, 1–3 large transfers within 48 h, often at night; INVESTMENT: escalating transfers to CRYPTO_EXCHANGE; JOB_TASK: small then growing top-ups to several new payees).
- Output: CSVs in `data/seed/`, a loader into SQLite (`make seed-local`) and BigQuery (`make seed-cloud`, using `bq load` or the Python client, dataset location asia-southeast1).

**Demo personas (must exist with exact IDs):**
| id | name | age | lang | story |
|---|---|---|---|---|
| cust_001 | Tan Mei Ling | 67 | zh | Retiree, balance about S$42,000, pays bills only. Demo: fake MAS officer, S$8,000 to new payee "Lee Wei Investigation Acct" |
| cust_002 | Raj Kumar | 29 | en | Gig worker. Demo: job-task scam, S$450 "top-up" to new payee |
| cust_003 | Nur Aisyah | 34 | en | Teacher. Demo (legit): S$3,200 deposit to new landlord, with tenancy agreement PDF |
| cust_004 | Daniel Lim | — | en | Analyst login for the console (Firebase Auth user, not a bank customer) |

## 3. Firestore collections

```
checks/{check_id}
  customer_id, created_at, status: SCORING|CHECKIN|ANALYSING|DONE|ERROR
  transfer: {payee_name, account_number, bank_name, dest_type, amount, currency, note}
  txn_risk: {score, reasons[], features{}}
  messages: [{role: assistant|customer, text, evidence_uris[], ts}]
  evidence: EvidenceAnalysis | null
  intel: IntelResult | null
  fusion: FusionResult | null
  customer_message: CustomerMessage | null
  latency_ms: {txn, evidence, intel, explainer, casefile, total}
  tokens: {in, out}
  customer_choice: PROCEEDED|COOL_OFF|CALLED_CONTACT|CANCELLED|null

cases/{case_id}      (only for AMBER/RED)
  check_id, customer_id, customer_name, amount, verdict, typology, confidence,
  case_file: CaseFile, status: OPEN|RELEASED|HELD|ESCALATED|REPORTED,
  assigned_to, created_at, decided_at, decision_note

audit/{auto_id}      actor, action, case_id, ts, note   (append-only)

watchlist/{normalised_value}
  type: PHONE|URL|DOMAIN|ACCOUNT, value, source: SEED|ANALYST_REPORT,
  reported_count, first_seen, last_seen, typologies[]

feedback/{auto_id}   check_id, helpful: bool, comment, ts
```
Seed the watchlist with about 30 fake entries (`data/seed/watchlist.json`). Include the demo scammer's phone number for cust_001's scenario, so the WATCHLIST_MATCH flag fires in the demo.

## 4. Evaluation dataset (`data/eval/`)

`cases.jsonl` holds **160 labelled cases**: 80 SCAM and 80 LEGIT (cut down to fit the 8-day deadline). Split them into `dev` (60) for prompt/threshold tuning and `test` (100), which is never used for tuning.

```json
{"id":"ev_0001","split":"test","label":"SCAM","typology":"JOB_TASK","language":"en",
 "transfer":{"customer_id":"cust_0xx","payee_name":"...","dest_type":"LOCAL_BANK","amount":450,"is_new_payee":true},
 "customer_answer":"A recruiter on Telegram said I need to top up to unlock my commission",
 "evidence":[{"type":"image","path":"data/eval/img/ev_0001.png"}],
 "expected_verdict_min":"AMBER"}
```

**Mix:**
- SCAM (80): GOV impersonation 16, investment 16, job/task 16, phishing 10, e-commerce 8, fake friend 8, romance 3, BEC invoice 3.
- LEGIT (hard negatives matter most): rent deposits, paying a new contractor, a family member asking for money with normal context, a genuine bank SMS, a real-looking invoice, a broker top-up, a charity donation, splitting a bill, a tuition fee, and a "my friend's new number" message that is genuine (with consistent context).
- Languages: about 65% en, 35% zh (Malay is dropped for the deadline).
- Evidence formats: about 60% image screenshots, 25% plain text, 10% PDF, 5% none.

**Screenshot renderer (`data/generate/render_chats.py`):** an HTML template that looks like a generic chat app (not WhatsApp or Telegram branding), rendered with Playwright to PNG at 1080×1920. It also renders SMS-style and email-style variants.

**Writing scam messages:** base them on *public* patterns from police and anti-scam advisories, rewritten with fictional names. Have Gemini draft variations with a fixed seed prompt, then **review them by hand**. Keep the generation prompt in `data/generate/prompts/`.
