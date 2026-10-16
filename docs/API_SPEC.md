# API Spec: PauseGuard

Base URL: `/api/v1`. JSON everywhere. FastAPI generates OpenAPI at `/docs`; keep it accurate, since it's part of the "real-world deployable" story.

Auth (prototype): customers use Firebase **anonymous auth** plus a selected demo persona (`customer_id` in the request body, validated against the seeded list). Analysts use Firebase email/password; the API verifies the ID token (`Authorization: Bearer <token>`) and checks the custom claim `role=analyst` for `/cases*` and `/metrics`. Write this auth limitation down in `SECURITY_PRIVACY.md`.

As built (phase 05, `backend/app/api/deps.py`):
- Customer routes accept any valid Firebase ID token (anonymous included). `customer_id` must be a customer of the synthetic bank (`cust_001`–`cust_501`); otherwise 422.
- `X-Admin-Token: <admin-reset-token>` is the ops/service credential: it passes every route (the smoke test and the benchmark use it) and is never rate-limited. A wrong admin token is a 403.
- `GET /checks/{id}/events` also accepts `?access_token=<ID token>`, because a browser `EventSource` can't set headers. Tokens are masked in log lines.
- `AUTH_DISABLED=true` (local dev only; the API refuses to start with it on Cloud Run) lets every request in as a local analyst.
- Check IDs are unguessable (ULID-style, 80 random bits) and act as the capability for a customer's own check; the API doesn't bind a check to the anonymous UID (prototype limitation).
- Rate limits on `POST /checks`: `RATE_LIMIT_CHECKS` per client IP (30/hour) and `RATE_LIMIT_CHECKS_PER_CUSTOMER` per `customer_id` (120/hour, generous because every judge shares the 3 personas). Over the limit → 429 `RATE_LIMITED`.
- `GET /personas` (public) returns the 3 demo personas for the persona picker.

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
Fields that don't apply are `null` (for example `question` on a GREEN answer). Header `X-PauseGuard-Eval: true` together with the admin token marks benchmark traffic (`is_eval`), which `/metrics` leaves out.

### `POST /uploads/sign`
`{"check_id":"...","filename":"chat.png","content_type":"image/png"}` → `{"upload_url":"https://storage.googleapis.com/...","gcs_uri":"gs://bucket/checks/chk_.../0-chat.png","expires_in":600,"headers":{"Content-Type":"image/png","x-goog-content-length-range":"0,10485760"}}`
Allowed types: png, jpeg, webp, pdf; audio (m4a, mp3, wav) is stretch. Max 10 MB, max 3 files per check, only while the check is `CHECKIN` (409 otherwise).
Then `PUT` the raw bytes to `upload_url` with exactly `headers` (GCS rejects other headers and files over 10 MB), and pass `gcs_uri` in `evidence_uris`. The object name is `<n>-<safe stem>.<extension of the content type>`. Locally (`UPLOAD_BACKEND=local`, the default off Cloud Run) `upload_url` points at the API itself (`PUT /api/v1/uploads/local/...`, HMAC-signed the same way, 10 min) and `gcs_uri` is a repo-relative path under `.local_uploads/`, so the web client has a single code path.

### `POST /checks/{check_id}/messages`
```json
{"text":"他说他是金管局的官员，我的账户涉及洗钱","quick_reply":"A government officer","evidence_uris":["gs://.../chat.png"]}
```
Optional `pasted_text` (max 4,000 characters): a chat the customer pasted ("paste the message"). It is analysed as text evidence, not as their own answer, and counts towards the limit of 3 evidence items (uploads + pasted text).
Every `evidence_uris` entry must be a `gcs_uri` that `POST /uploads/sign` returned for this check (422 otherwise), so a request can't point the model at other objects. A check that isn't `CHECKIN` (already answered) is a 409; an unknown check a 404.
Response 200 (after analysis; also streamed as events):
```json
{"check_id":"...","status":"DONE",
 "verdict":"RED","action":"HOLD_FOR_REVIEW","needs_review":false,
 "typology":"GOV_OFFICIAL_IMPERSONATION","confidence":0.93,
 "top_flags":[{"code":"SAFE_ACCOUNT","severity":"HIGH","quote":"transfer to the safe account","evidence_index":0,"box_2d":[410,60,470,940]}],
 "customer_message":{"language":"zh","headline":"...","body":"...","flag_explanations":[...],"next_steps":[...]},
 "case_id":"case_01J...","latency_ms":{"total":4210}}
```
Possible extra turn: `status:"CHECKIN"` with a follow-up `question` (max one follow-up; not implemented in the MVP).
The response is sent at the orchestrator's `done` event. The analyst-facing part (case file ∥ web search) keeps running in the same process after the response, which is why Cloud Run runs with CPU always allocated (DEPLOYMENT §2). If no `done` arrives within `AGENT_TIMEOUT_SECONDS` + 8 s, or the pipeline crashes before it, the answer is AMBER, `needs_review:true`, `typology:"UNKNOWN"`, with a case (deterministic case file) for an analyst: never an error, never GREEN.

### `GET /checks/{check_id}/events` (SSE)
Event types: `status` (`SCORING|ANALYSING_EVIDENCE|CHECKING_INTEL|DECIDING|WRITING|DONE`), `partial` (e.g. a flag found), `done` (full result), `error`. The MVP UI may poll `GET /checks/{id}` every 700 ms instead.
Each event is `event: <type>` + `data: {"type","stage","data"}` (a `ProgressEvent`); the `done` event's `data` is the `POST /messages` response. Events already sent are replayed when a client connects; a finished check sends `done` at once; the stream closes after `done` or `error` (`error` after 120 s without a result). Events live in memory on the instance that runs the analysis, so the route also reads the check document every 700 ms: a client connected to another instance still gets `done`.
Order emitted by the orchestrator: `status ANALYSING_EVIDENCE`, `status CHECKING_INTEL`, `partial ANALYSING_EVIDENCE {flags, typology}`, `partial CHECKING_INTEL {watchlist_matches}`, `status DECIDING`, `partial DECIDING {verdict, action, top_flags}` (the UI can show the verdict and boxes now), `status WRITING`, `done DONE {…the response…}`. `latency_ms.verdict` is the time to the `partial DECIDING` event and `latency_ms.total` the time to `done`. The case file is written after `done` (the case document exists from `done`, and its `case_file` is filled in a few seconds later).

### `GET /checks/{check_id}`
Returns the full check document (customer-safe fields only: no case file).

### `POST /checks/{check_id}/choice`
`{"choice":"COOL_OFF"|"CALLED_CONTACT"|"PROCEEDED"|"CANCELLED","confirmed":false}` → 200 `{"check_id":"...","customer_choice":"..."}`. PROCEEDED is only allowed for GREEN, or for AMBER after the confirm step (`"confirmed": true`, sent by the "I understand the risk" dialog; without it 409). It is rejected for RED with 409. A check without a verdict yet is a 409.

### `POST /checks/{check_id}/feedback`
`{"helpful":true,"comment":"..."}` → 201 `{"feedback_id":"..."}`

## Analyst endpoints (role=analyst)

### `GET /cases?status=OPEN&limit=50`
List of case summaries (the console mainly uses the Firestore realtime listener; this endpoint is for tests and fallback).

### `GET /cases/{case_id}`
Full case (`CaseDetail`): `case` (with `case_file`, null for a few seconds after the case appears), `transfer`, `txn_risk`, `messages` (the check-in, raw text), `evidence`, `evidence_links` (signed read URLs, 5 min; `index` matches the flags' `evidence_index`), `intel`, `fusion`, `customer_choice`, `audit` (oldest first).

### `GET /cases/{case_id}/history`
The customer's outgoing payments in the 90 days before the check, for the console's risk chart: `{"customer_id","as_of","days":[{"day":"2026-10-10","amount":120.5,"count":2}, …],"median_debit_90d":43.5,"transfer_amount":8000}`. One entry per Singapore day, empty days included; `median_debit_90d` is the median single debit (what `amount_vs_median_90d` compares with). A separate route because the BigQuery query takes about a second and only the Risk tab needs it.

### `POST /cases/{case_id}/decision`
`{"action":"RELEASE"|"HOLD"|"ESCALATE"|"REPORT_SCAM","note":"Called customer, confirmed MAS impersonation"}`
- Writes an `audit` entry and updates the case status.
- `REPORT_SCAM` upserts every extracted phone number, URL, domain and account into `watchlist` (source ANALYST_REPORT, increments reported_count).
- Response: `{"case_id":"...","status":"REPORTED","watchlist_added":3}` (`watchlist_added` drives the "N entities added" toast).
- As built: the entities are the evidence agent's, the phones/URLs/accounts in the pasted chat, and the payee account; not the customer's own answer and never their trusted contact. A URL is reported as its **domain**, except on shared platforms (t.me, wa.me, bit.ly, docs.google.com…), where only that exact link is reported (a bare shared host is skipped); `.gov.sg`, `.gov`, `.edu.sg` and `.mil` domains are never reported. The case's typology is added to the entries. A second audit entry (`WATCHLIST_ADD`) lists what was reported.

### `GET /metrics?range=today|7d`
```json
{"checks":312,"verdicts":{"GREEN":240,"AMBER":51,"RED":21},"money_protected_sgd":184500,
 "false_positive_rate":0.048,"latency_ms":{"p50":3900,"p95":8100},
 "top_typologies":[{"typology":"JOB_TASK","count":19}, ...],"cost_per_check_usd":0.0041}
```
Also `verdicts_over_time` (`[{"start":"2026-10-11T09:00:00+08:00","GREEN":3,"AMBER":1,"RED":1}, …]`: hourly since 00:00 Singapore time for `today`, per Singapore day for `7d`, empty buckets included) and `latency_histogram` (`[{"from_ms":0,"to_ms":2000,"count":4}, …, {"from_ms":20000,"to_ms":null,"count":0}]`, the same latencies as the percentiles) for the dashboard charts.
From `checks_analytics` (latest snapshot per check; benchmark rows excluded). `today` starts at 00:00 Singapore time; `7d` is the last 168 hours. Money protected = RED amounts not released by an analyst + AMBER amounts the customer cancelled or paused (COOL_OFF). False-positive rate = RED checks released ÷ RED checks (PRD A5). Latency = check-in answer → full customer result (`latency_ms.total`), checks with a check-in only. Top typologies: AMBER/RED checks, top 5. `cost_per_check_usd` is null until `GEMINI_PRICE_IN_USD_PER_MTOK` / `GEMINI_PRICE_OUT_USD_PER_MTOK` are set from the published price list (phase 09).

### `GET /watchlist?limit=500`
Watchlist entries (`WatchlistEntry`: type, normalised value, source SEED|ANALYST_REPORT, reported_count, first/last seen, typologies), most recently seen first, for the console's Watchlist page. Analysts only, read only: only `REPORT_SCAM` and the seed write to it.

## Ops

- `GET /health` → `{"ok":true,"model":"<GEMINI_MODEL>","data_backend":"bigquery","dependencies":{"firestore":true,"bigquery":true,"gemini":true}}` (locally the key is `sqlite`). It checks the dependencies so uptime checks catch real outages: one Firestore read on every call, BigQuery `SELECT 1` (no table, nothing billed) cached for 60 s, and Gemini `count_tokens` (free, nothing generated) cached for 10 minutes; a failure is cached for 60 s only. **503 with the same body** when any of them fails. Not `/healthz`: Cloud Run reserves some paths ending in `z` and answers `/healthz` itself with a 404 (it stays as a local-only alias).
- `POST /admin/reset-demo` (needs an admin token from Secret Manager, `X-Admin-Token`): resets the demo personas' checks and cases, so the live demo can be re-run. Response `{"checks_deleted":1,"cases_deleted":1,"watchlist_deleted":1,"seed_restored":30}`; ANALYST_REPORT watchlist entries are deleted and the seed entries are put back as seeded (a REPORT_SCAM bumps their counts); audit and analytics are kept. Cloud Scheduler calls it every 6 hours.
- `POST /admin/purge-eval` (admin token): deletes every check marked as benchmark traffic (`X-PauseGuard-Eval: true`) and the cases they opened, so a benchmark run against the live stack leaves nothing in the analyst queue. Response `{"checks_deleted":100,"cases_deleted":52}`; their `checks_analytics` rows stay (marked `is_eval`, excluded from `/metrics`). `eval/run_benchmark.py --api` calls it at the end of a run.
- `POST /admin/selftest` (admin token): runs the Aisyah GREEN scenario end to end through the real agents, as the app does: start the check, attach her tenancy PDF (written to the evidence bucket by the API itself), answer the check-in. Response `{"passed":true,"scenario":"aisyah","expected":["GREEN"],"verdict":"GREEN","needs_review":false,"check_id":"chk_…","latency_ms":5210,"reason":null}`; **503 with the same body** when it isn't GREEN without review (`reason` says why, e.g. `expected GREEN, got AMBER + needs_review`). The check is marked as test traffic (`is_eval`, kept out of `/metrics`) and the next reset removes it. It logs `selftest_passed` / `selftest_failed`. Cloud Scheduler calls it daily (see `DEPLOYMENT.md` §7).

## Errors

`{"error":{"code":"VALIDATION_ERROR|NOT_FOUND|FORBIDDEN|ANALYSIS_TIMEOUT|INTERNAL","message":"..."}}`. An analysis timeout is **not** returned as an error to the customer; it returns AMBER with `needs_review:true`.

As built, the codes and their statuses: `VALIDATION_ERROR` (422, also 413/415 for local uploads; `details` lists `{loc,msg,type}` per field, never the input), `UNAUTHORIZED` (401: no or invalid ID token), `FORBIDDEN` (403: no analyst claim, wrong admin token, bad signed URL), `NOT_FOUND` (404), `CONFLICT` (409: the check or case is in the wrong state), `RATE_LIMITED` (429), `INTERNAL` (500, a generic message; the traceback is only in the redacted log). `ANALYSIS_TIMEOUT` is reserved and never sent.
