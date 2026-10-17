# Deployment: PauseGuard

The target is a public live link that judges can open, with the backend in Singapore.

## 0. Prerequisites (the human does these once)

1. A Google Cloud project with billing (use hackathon or trial credits if you were given any). Note the `PROJECT_ID`.
2. Install: `gcloud`, `firebase-tools` (`npm i -g firebase-tools`), Docker (optional; Cloud Build can build the image), Python 3.12 + `uv`, Node 20+.
3. `gcloud auth login && gcloud auth application-default login && gcloud config set project $PROJECT_ID`
4. `firebase login`, then add Firebase to the same GCP project in the Firebase console, and create a Web app to get the config JSON.
5. Set a **budget alert** (Billing › Budgets), e.g. US$50 with 50/90/100% alerts.

## 1. One-time infrastructure (`make infra` → `infra/setup.sh`, idempotent)

`infra/setup.sh` (flags checked against gcloud 588, 11 Oct 2026) looks for each resource before creating it, so it is safe to re-run. It reads the project from `GOOGLE_CLOUD_PROJECT` in `.env`.

| Step | What it creates (all data in `asia-southeast1`) |
|---|---|
| APIs | Run, Vertex AI, BigQuery, Firestore, Storage, Secret Manager, Cloud Build, Artifact Registry, Trace + Telemetry (OTLP), Logging, IAM Credentials (signBlob for the V4 signed URLs), Firebase Hosting/Rules, Identity Toolkit |
| Firestore | `(default)`, native mode |
| BigQuery | dataset `pauseguard` (tables come from `make seed-cloud`) |
| Cloud Storage | `gs://$PROJECT-pauseguard-evidence`: uniform access, public access prevention, `infra/lifecycle.json` (delete after 30 days), `infra/cors.json` (PUT/GET from the Hosting origins + localhost; headers `Content-Type`, `x-goog-content-length-range`) |
| Artifact Registry | docker repo `pauseguard` (the API image) |
| Secret Manager | `admin-reset-token` (random, replicated in `asia-southeast1` only) |
| `pauseguard-api@` (runtime) | project: `aiplatform.user`, `bigquery.jobUser`, `datastore.user`, `logging.logWriter`, `cloudtrace.agent`; dataset: `WRITER` (= `bigquery.dataEditor`, via the dataset's access list, because `bq add-iam-policy-binding -d` needs allowlisting); bucket: `storage.objectAdmin`; secret: `secretAccessor`; itself: `iam.serviceAccountTokenCreator` |
| `pauseguard-build@` (build) | project: `run.builder`; passed as `--build-service-account`, so source deploys don't depend on the Compute Engine default account |

Then: `make seed-cloud` (BigQuery tables + the Firestore watchlist and personas) and `make analyst` (`infra/set_analyst_claim.py`: creates or refreshes the demo analyst `analyst@harbourbank.example` and sets the custom claim `role=analyst`). The Firebase console steps can't be scripted without upgrading to Identity Platform: **Authentication → Get started → enable Anonymous and Email/Password**.

## 2. Backend → Cloud Run (`make deploy-api`)

```bash
gcloud run deploy pauseguard-api --project $PROJECT --region asia-southeast1 --quiet \
  --source backend --image asia-southeast1-docker.pkg.dev/$PROJECT/pauseguard/pauseguard-api \
  --build-service-account projects/$PROJECT/serviceAccounts/pauseguard-build@$PROJECT.iam.gserviceaccount.com \
  --service-account pauseguard-api@$PROJECT.iam.gserviceaccount.com \
  --env-vars-file infra/cloudrun.env.yaml --set-secrets ADMIN_RESET_TOKEN=admin-reset-token:latest \
  --allow-unauthenticated --min-instances $MIN_INSTANCES --max-instances 5 --concurrency 20 \
  --memory 1Gi --cpu 1 --timeout 180 --no-cpu-throttling --cpu-boost
```
The env vars live in `infra/cloudrun.env.yaml` (no secrets), because `ALLOWED_ORIGINS` contains commas, which `--set-env-vars` would split. `backend/.gcloudignore` keeps the local `.venv` out of the upload. The API does its own auth (Firebase tokens), so the service is public. `MIN_INSTANCES` is 0 while building; `make deploy-api MIN_INSTANCES=1` from submission day on (§7).

Why these flags (phase 05): `POST /checks/{id}/messages` answers the customer at the `done` event and then keeps writing the case file and the web findings for up to `CASEFILE_TIMEOUT_SECONDS` (25 s) in the same process. With the default request-based billing, Cloud Run throttles CPU after the response and that work would stall, so the console would wait for its case summary; `--no-cpu-throttling` (instance-based billing) keeps CPU allocated. It costs more only while an instance is up (≈ US$2.07/day for one always-on 1 vCPU/1 GiB instance in Singapore, Tier 2; see COSTS.md with `--min-instances 1`; scale-to-zero otherwise). `--timeout 180` covers the SSE stream (it closes after `done`, at most 120 s). `--cpu-boost` shortens cold starts. Uploads go to GCS automatically on Cloud Run (`UPLOAD_BACKEND` defaults to `gcs` when `K_SERVICE` is set; `local` is refused there).

**Health route:** `GET /health`. Cloud Run's front end reserves some paths ending in `z` and answers `/healthz` itself with a Google 404, so uptime checks must use `/health` (`/healthz` remains a local alias).

`backend/Dockerfile`: python:3.12-slim, `uv sync --frozen`, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## 3. Frontend → Firebase Hosting (`make deploy-web`)

The Firebase web config lives in the git-ignored `web/.env.production.local`. `make deploy-web` reads the live API URL from Cloud Run, builds with `VITE_API_BASE_URL=<that URL>` (an env var beats the `.env` files in Vite), then runs `firebase deploy --only hosting,firestore:rules,firestore:indexes`. `firebase.json`: every path is rewritten to `/index.html` (SPA); `index.html` and deep links are `no-cache` and the hashed `/assets/**` are immutable, so a redeploy never leaves a browser with an old `index.html` pointing at deleted assets. Rules: `infra/firestore.rules` (clients may `get` one check by ID; only analysts read cases, audit, watchlist and feedback; no client writes). We call Cloud Run directly with CORS rather than a Hosting `/api/**` rewrite: Hosting rewrites cut requests at 60 s, which would break SSE.

New composite indexes take a few minutes to build after the first deploy; until then `/cases` answers 500 (`FailedPrecondition: index is currently building`), and even after `gcloud firestore indexes composite list` says READY it can flap for about a minute.

## 4. Smoke test (`make smoke` → `scripts/smoke.sh`)

`GET /health` → Hosting page + SPA deep link + CORS preflight from the Hosting origin → Firebase Auth with real tokens (an anonymous customer starts a check and gets 403 on `/cases`; the demo analyst gets 200) → the 3 demo scenarios through the API (`scripts/demo_curl.sh` with the admin token from Secret Manager: upload, answer, SSE, verdict GREEN / RED / AMBER-or-RED, case file, REPORT_SCAM) → `POST /admin/reset-demo`. `AUTH=0` skips the Auth step; `SCENARIOS=tan` runs one scenario.

## 5. CI (optional, nice for judges)

GitHub Actions: on PR run `make lint test` (backend + web). On push to `main` there is an optional manual deploy workflow using Workload Identity Federation (no keys). Skip this if time is short; don't store keys in GitHub.

## 6. Cost estimate (fill in real numbers in `docs/COSTS.md` during phase 11)

| Item | Prototype (1 month, demo traffic) | Pilot (1 bank, 50k checks/month) |
|---|---|---|
| Cloud Run | ~free tier (scale to zero) | low tens of USD |
| Vertex AI Gemini Flash | cents (hundreds of checks) | tokens/check × 50k × price; compute from the benchmark |
| BigQuery | free tier (< 1 GB) | low |
| Firestore | free tier | low |
| Cloud Storage | negligible | low |
| Firebase Hosting | free tier | free/low |

Use the **measured tokens per check** from the benchmark and the **current published prices** (with the date and URL) to fill in the pilot column. Don't guess prices.

## 7. Keeping it up during the evaluation period (mandatory rule)

The rules say the prototype must stay functional **throughout evaluation**, and there are no retries if anything is down. The evaluation dates aren't published, so keep everything running **from submission until results are announced** (and through the 4 Dec finale if shortlisted).

1. **No cold starts or scale-to-zero surprises:** `--min-instances 1` on `pauseguard-api` from submission day onward (this costs a few dollars a month; it's worth it). Set `--max-instances 5` and `--concurrency 20`.
2. **Uptime checks plus alerts:** create Cloud Monitoring uptime checks on `https://<hosting-domain>/` and `https://<api>/health` (every 5 min; not `/healthz`, which Cloud Run reserves), with an email/SMS alert policy to the team. `/health` must also do a cheap dependency check: Firestore read, BigQuery `SELECT 1` (cached for 60 s), and model reachability (cached for 10 min, so it doesn't spend tokens on every probe).
3. **A deep synthetic check once a day:** a Cloud Scheduler job calls `POST /admin/selftest`, which runs the Aisyah (GREEN) scenario end to end through Gemini and logs a pass/fail metric; alert on failure.
4. **Self-healing demo data:** judges will click around, report scams and hold cases. Run a Cloud Scheduler job every 6 hours that calls `POST /admin/reset-demo` (the 3 personas' checks and cases, plus watchlist entries added by ANALYST_REPORT; the seed entries are kept). Each judge's new checks still work in between resets.
5. **Gemini quota:** check the Vertex AI quota for the model in your region/`global` and request an increase if it's low. Retry with exponential backoff on 429. Keep the AMBER + review fallback so the UI never breaks.
6. **Billing must not stop:** use a **budget alert only, never an automatic billing cut-off**. Check the free-trial or credit expiry date (it must be later than the evaluation period), and add a card or credits if needed.
7. **Rate limits that don't lock judges out:** per-IP limit of 30 checks/hour (not lower). The persona picker and demo logins are always visible on the landing page.
8. **Freeze the release:** tag `v1.0-submission` and deploy exactly that tag. During evaluation, fix only critical bugs, in a branch, smoke-tested first, then redeploy. Never delete or rename the Cloud Run service, Firebase site, bucket or dataset.
9. **Keep the GitHub repo public** throughout. Don't rename, transfer or make it private.
10. **Check from outside:** open the live link, the video and the repo in an incognito window, on mobile data, from another device, the day after submitting and then weekly.

### As built (phase 10 pass B, `make uptime` → `infra/uptime.sh`, idempotent)

| Item | What exists |
|---|---|
| Cloud Run | `make deploy-api`: **min 0** (the user's cost decision, 16 Oct; see DECISIONS), max 5, concurrency 20, CPU always allocated, startup CPU boost. A cold start takes ≈ 8 s; the landing page sends a background `GET /health` on load, so the API is usually awake by the time a judge picks a persona. `make deploy-api MIN_INSTANCES=1` (≈ US$2.07/day, COSTS.md) for a live demo or a known judging day |
| `/health` | Firestore read (every call), BigQuery `SELECT 1` (60 s cache, nothing billed), Gemini `count_tokens` (10 min cache, free); 503 + which dependency on failure |
| Uptime checks | `pauseguard-web` (`https://<project>.web.app/`, body must contain "PauseGuard"), every 5 min from all 6 regions, 20 s timeout, SSL validated. `pauseguard-api-health` (`<api>/health`) only with `make uptime API_UPTIME=1`: with CPU always allocated, Cloud Run bills an instance for its whole life (idle up to 15 min), so a 5-minute probe keeps one billed around the clock, ≈ the cost of min 1. Without it, the API is watched by the Scheduler jobs: a failed 6-hourly reset or daily selftest attempt emails (so an API outage is noticed within 6 h), and `make smoke` checks `/health` |
| Alert policies | "PauseGuard: live site or API down" (a check failing from 2+ regions for 5 min) and "PauseGuard: selftest or scheduled job failed" (log alert: `selftest_failed` in the API logs, or a `pauseguard-*` Scheduler attempt at ERROR; at most one email an hour), both to the `ALERT_EMAIL` channel |
| Scheduler (asia-southeast1, Asia/Singapore) | `pauseguard-reset-demo` `0 */6 * * *` → `POST /api/v1/admin/reset-demo`; `pauseguard-selftest` `30 7 * * *` → `POST /api/v1/admin/selftest` (no retries, 120 s deadline). Both send `X-Admin-Token`; re-run `make uptime` after rotating the secret. `make uptime RUN_JOBS=1` runs both once |
| Gemini quota | Standard PayGo on the `global` endpoint: throughput limits are per organisation and rise with spend (Flash Tier 1 = 2M tokens/min, checked 16 Oct 2026), so there is no project quota to raise; a check uses ≈ 6k tokens. 429/503 are retried by the genai client (3 attempts, 0.5 s → 1 s backoff with jitter), then the AgentRunner's retry, then AMBER + review |
| Rate limit | 30 checks/hour per IP, 120/hour per customer (`infra/cloudrun.env.yaml`) |
| Cloud Trace | ADK spans exported via telemetry.googleapis.com (`roles/cloudtrace.agent` includes `telemetry.traces.write`), one `pauseguard.check` trace per answer, no message content |
