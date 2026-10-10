# API Spec: PauseGuard

Base URL: `/api/v1`. JSON everywhere. FastAPI generates OpenAPI at `/docs`; keep it accurate, since it's part of the "real-world deployable" story.

Auth (prototype): customers use Firebase **anonymous auth** plus a selected demo persona (`customer_id` in the request body, validated against the seeded list). Analysts use Firebase email/password; the API verifies the ID token (`Authorization: Bearer <token>`) and checks the custom claim `role=analyst` for `/cases*` and `/metrics`. Write this auth limitation down in `SECURITY_PRIVACY.md`.

## Customer endpoints

### `POST /checks`
Start a check for a transfer.
```json
// request
{"customer_id":"cust_001",
 "transfer":{"payee_name":"Lee Wei Investigation Acct","account_number":"123-45678-9","bank_name":"Harbour Bank",
             "dest_type":"LOCAL_BANK","amount":8000,"currency":"SGD","note":"case 2231"},
 "language":"zh"}
// response 201
{"check_id":"chk_01J...","status":"CHECKIN",
 "txn_risk":{"score":65,"reasons":[{"code":"NEW_PAYEE","label":"First payment to this account","points":20}, ...]},
 "question":{"text":"这笔转账是谁让您付的？有人先联系您吗？","quick_replies":["A government officer","A job recruiter","An investment group","A friend or family member","A seller","No one, it's my own payment"]}}
// or, if low risk:
{"check_id":"...","status":"DONE","verdict":"GREEN","customer_message":{...}}
```

### `POST /uploads/sign`
`{"check_id":"...","filename":"chat.png","content_type":"image/png"}` → `{"upload_url":"https://storage.googleapis.com/...","gcs_uri":"gs://bucket/checks/chk_.../chat.png","expires_in":600}`
Allowed types: png, jpeg, webp, pdf; audio (m4a, mp3, wav) is stretch. Max 10 MB, max 3 files per check.

### `POST /checks/{check_id}/messages`
```json
{"text":"他说他是金管局的官员，我的账户涉及洗钱","quick_reply":"A government officer","evidence_uris":["gs://.../chat.png"]}
```
Response 200 (after analysis; also streamed as events):
```json
{"check_id":"...","status":"DONE",
 "verdict":"RED","action":"HOLD_FOR_REVIEW","needs_review":false,
 "typology":"GOV_OFFICIAL_IMPERSONATION","confidence":0.93,
 "top_flags":[{"code":"SAFE_ACCOUNT","severity":"HIGH","quote":"transfer to the safe account","evidence_index":0,"box_2d":[410,60,470,940]}],
 "customer_message":{"language":"zh","headline":"...","body":"...","flag_explanations":[...],"next_steps":[...]},
 "case_id":"case_01J...","latency_ms":{"total":4210}}
```
Possible extra turn: `status:"CHECKIN"` with a follow-up `question` (max one follow-up).

### `GET /checks/{check_id}/events` (SSE)
Event types: `status` (`SCORING|ANALYSING_EVIDENCE|CHECKING_INTEL|DECIDING|WRITING|DONE`), `partial` (e.g. a flag found), `done` (full result), `error`. The MVP UI may poll `GET /checks/{id}` every 700 ms instead.

### `GET /checks/{check_id}`
Returns the full check document (customer-safe fields only: no case file).

### `POST /checks/{check_id}/choice`
`{"choice":"COOL_OFF"|"CALLED_CONTACT"|"PROCEEDED"|"CANCELLED"}` → 200. PROCEEDED is only allowed for GREEN, or for AMBER after the confirm step. It is rejected for RED with 409.

### `POST /checks/{check_id}/feedback`
`{"helpful":true,"comment":"..."}`

## Analyst endpoints (role=analyst)

### `GET /cases?status=OPEN&limit=50`
List of case summaries (the console mainly uses the Firestore realtime listener; this endpoint is for tests and fallback).

### `GET /cases/{case_id}`
Full case: case file, evidence signed read URLs (5 min), flags, txn features, intel, audit history.

### `POST /cases/{case_id}/decision`
`{"action":"RELEASE"|"HOLD"|"ESCALATE"|"REPORT_SCAM","note":"Called customer, confirmed MAS impersonation"}`
- Writes an `audit` entry and updates the case status.
- `REPORT_SCAM` upserts every extracted phone number, URL, domain and account into `watchlist` (source ANALYST_REPORT, increments reported_count).

### `GET /metrics?range=today|7d`
```json
{"checks":312,"verdicts":{"GREEN":240,"AMBER":51,"RED":21},"money_protected_sgd":184500,
 "false_positive_rate":0.048,"latency_ms":{"p50":3900,"p95":8100},
 "top_typologies":[{"typology":"JOB_TASK","count":19}, ...],"cost_per_check_usd":0.0041}
```

## Ops

- `GET /healthz` → `{"ok":true,"model":"<GEMINI_MODEL>","data_backend":"bigquery"}`
- `POST /admin/reset-demo` (needs an admin token from Secret Manager): resets the demo personas' checks and cases, so the live demo can be re-run.
- `POST /admin/selftest` (admin token): runs the Aisyah GREEN scenario end to end through Gemini and returns pass/fail plus latency. Cloud Scheduler calls it daily (see `DEPLOYMENT.md` §7).
- `GET /healthz` also checks the dependencies (Firestore, BigQuery and model reachability, cached) so uptime checks catch real outages.

## Errors

`{"error":{"code":"VALIDATION_ERROR|NOT_FOUND|FORBIDDEN|ANALYSIS_TIMEOUT|INTERNAL","message":"..."}}`. An analysis timeout is **not** returned as an error to the customer; it returns AMBER with `needs_review:true`.
