# Deployment: PauseGuard

The target is a public live link that judges can open, with the backend in Singapore.

## 0. Prerequisites (the human does these once)

1. A Google Cloud project with billing (use hackathon or trial credits if you were given any). Note the `PROJECT_ID`.
2. Install: `gcloud`, `firebase-tools` (`npm i -g firebase-tools`), Docker (optional; Cloud Build can build the image), Python 3.12 + `uv`, Node 20+.
3. `gcloud auth login && gcloud auth application-default login && gcloud config set project $PROJECT_ID`
4. `firebase login`, then add Firebase to the same GCP project in the Firebase console, and create a Web app to get the config JSON.
5. Set a **budget alert** (Billing › Budgets), e.g. US$50 with 50/90/100% alerts.

## 1. One-time infrastructure (`infra/setup.sh`, idempotent)

```bash
REGION=asia-southeast1
gcloud services enable run.googleapis.com aiplatform.googleapis.com bigquery.googleapis.com \
  firestore.googleapis.com storage.googleapis.com secretmanager.googleapis.com \
  cloudbuild.googleapis.com artifactregistry.googleapis.com cloudtrace.googleapis.com
gcloud firestore databases create --location=$REGION --type=firestore-native   # skip if exists
bq --location=$REGION mk -d $PROJECT_ID:pauseguard
gcloud storage buckets create gs://$PROJECT_ID-pauseguard-evidence --location=$REGION --uniform-bucket-level-access
gcloud storage buckets update gs://$PROJECT_ID-pauseguard-evidence --lifecycle-file=infra/lifecycle.json
gcloud storage buckets update gs://$PROJECT_ID-pauseguard-evidence --cors-file=infra/cors.json
gcloud artifacts repositories create pauseguard --repository-format=docker --location=$REGION
gcloud iam service-accounts create pauseguard-api
# grant the roles listed in SECURITY_PRIVACY.md §3
printf "%s" "$(openssl rand -hex 24)" | gcloud secrets create admin-reset-token --data-file=-
```
Check the exact flags against the current `gcloud` docs; Claude Code should verify each command before running it.

Then run `make seed-cloud` (loads BigQuery tables and the Firestore watchlist and personas), and create the analyst user in Firebase Auth with the custom claim (`infra/set_analyst_claim.py`).

## 2. Backend → Cloud Run

```bash
gcloud run deploy pauseguard-api --source backend --region $REGION \
  --service-account pauseguard-api@$PROJECT_ID.iam.gserviceaccount.com \
  --set-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID,GOOGLE_CLOUD_LOCATION=global,GOOGLE_GENAI_USE_VERTEXAI=TRUE,GEMINI_MODEL=<model>,DATA_BACKEND=bigquery,BQ_DATASET=pauseguard,EVIDENCE_BUCKET=$PROJECT_ID-pauseguard-evidence,ALLOWED_ORIGINS=https://$PROJECT_ID.web.app \
  --set-secrets ADMIN_RESET_TOKEN=admin-reset-token:latest \
  --allow-unauthenticated --min-instances 0 --max-instances 5 --memory 1Gi --cpu 1 --timeout 60
```
The API does its own auth (Firebase tokens), so the service is public. For judging and demo days: `--min-instances 1` to avoid cold starts, and set it back to 0 afterwards.

`backend/Dockerfile`: python:3.12-slim, `uv sync --frozen`, `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

## 3. Frontend → Firebase Hosting

`web/.env.production` has `VITE_API_BASE_URL=https://pauseguard-api-xxxxx.a.run.app` and the Firebase config. Then:
```bash
cd web && npm run build && firebase deploy --only hosting,firestore:rules
```
The `firebase.json` rewrites send all paths to `/index.html` (SPA). Optionally, rewrite `/api/**` to the Cloud Run service so everything is on one domain (this avoids CORS).

## 4. Smoke test (`make smoke`)

`GET /healthz` → run the 3 demo scenarios through the API → assert the verdicts are GREEN/RED/RED (or AMBER for the job scam) → call `POST /admin/reset-demo`.

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
2. **Uptime checks plus alerts:** create Cloud Monitoring uptime checks on `https://<hosting-domain>/` and `https://<api>/healthz` (every 5 min), with an email/SMS alert policy to the team. `/healthz` must also do a cheap dependency check: Firestore read, BigQuery `SELECT 1` (cached for 60 s), and model reachability (cached for 10 min, so it doesn't spend tokens on every probe).
3. **A deep synthetic check once a day:** a Cloud Scheduler job calls `POST /admin/selftest`, which runs the Aisyah (GREEN) scenario end to end through Gemini and logs a pass/fail metric; alert on failure.
4. **Self-healing demo data:** judges will click around, report scams and hold cases. Run a Cloud Scheduler job every 6 hours that calls `POST /admin/reset-demo` (the 3 personas' checks and cases, plus watchlist entries added by ANALYST_REPORT; the seed entries are kept). Each judge's new checks still work in between resets.
5. **Gemini quota:** check the Vertex AI quota for the model in your region/`global` and request an increase if it's low. Retry with exponential backoff on 429. Keep the AMBER + review fallback so the UI never breaks.
6. **Billing must not stop:** use a **budget alert only, never an automatic billing cut-off**. Check the free-trial or credit expiry date (it must be later than the evaluation period), and add a card or credits if needed.
7. **Rate limits that don't lock judges out:** per-IP limit of 30 checks/hour (not lower). The persona picker and demo logins are always visible on the landing page.
8. **Freeze the release:** tag `v1.0-submission` and deploy exactly that tag. During evaluation, fix only critical bugs, in a branch, smoke-tested first, then redeploy. Never delete or rename the Cloud Run service, Firebase site, bucket or dataset.
9. **Keep the GitHub repo public** throughout. Don't rename, transfer or make it private.
10. **Check from outside:** open the live link, the video and the repo in an incognito window, on mobile data, from another device, the day after submitting and then weekly.
