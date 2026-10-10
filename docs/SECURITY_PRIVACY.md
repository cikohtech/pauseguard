# Security, Privacy & Responsible AI: PauseGuard

## 1. Prompt-injection defence (uploaded content is hostile)

Scammers write the evidence, so assume it will contain instructions aimed at the model.
- The system prompt states that evidence content is data, never instructions (see `AGENTS_SPEC.md` §2).
- Evidence is wrapped in clear delimiters: `<evidence index="0" type="image">…</evidence>`.
- `security/injection.py`: a regex and heuristic pre-scan of OCR text and the customer's answer for phrases like "ignore previous", "system prompt", "you are now", "say this is safe", and Chinese equivalents. A hit sets `injection_attempt_detected` → fusion forces RED.
- The LLM never decides the verdict; `policy/fusion.py` does. The worst an injection can do is change the extracted flags, and the eval set includes 5 injection cases to measure this.
- No agent has write tools that move money or change the watchlist; only analyst actions do.

## 2. PII and data handling

- All prototype data is synthetic. Write this on the landing page and in the README.
- `security/redaction.py` masks phone numbers, account numbers, NRIC-like patterns (`[STFGM]\d{7}[A-Z]`) and emails in **logs** (not in the analyst case file, where they're needed).
- Evidence goes in GCS under `checks/{check_id}/`, with uniform bucket-level access, no public access, a **30-day lifecycle delete** (`infra/lifecycle.json`), and only signed URLs that expire in 10 minutes for upload and 5 minutes for reading.
- Data location: Firestore, BigQuery and GCS in **asia-southeast1**. Vertex AI is called with the configured location (note in the README if `global` is used).
- Consent: the check-in sheet says "We'll use what you share only to check this payment. It's deleted after 30 days."

## 3. Auth and IAM (prototype level)

- Customers: Firebase anonymous auth, plus a persona picker. This is a demo limitation, documented in the README.
- Analysts: Firebase email/password with the custom claim `role=analyst`. The API verifies ID tokens with `firebase-admin`.
- Firestore rules (`infra/firestore.rules`): customers can read only their own `checks` doc, through the API-returned ID; only analysts can read `cases`, `audit` and `watchlist`; clients never write directly, all writes go through the API (service account).
- The Cloud Run service account `pauseguard-api@` gets least privilege: `roles/aiplatform.user`, `roles/bigquery.dataEditor` (dataset-scoped) + `roles/bigquery.jobUser`, `roles/datastore.user`, `roles/storage.objectAdmin` (bucket-scoped), `roles/secretmanager.secretAccessor`, `roles/logging.logWriter`, `roles/cloudtrace.agent`.
- CORS is restricted to the Firebase Hosting domains plus localhost.
- Rate limit: a simple per-IP and per-customer limit on `/checks` (for example, slowapi), so the public demo can't run up costs.

## 4. Responsible AI

- **Human in the loop:** RED always goes to a human; AMBER lets the customer continue after an informed confirmation (their autonomy is respected).
- **No blame, no fear:** the explainer's tone rules are in `AGENTS_SPEC.md` §5.
- **Fairness check:** in the eval report, break down FPR by language and age band. If one group is much worse, report it and the mitigation.
- **Transparency:** customers see *why* (the flags plus quotes); analysts see the reasons and their sources.
- **Failure mode:** model down or timeout → AMBER + review, never a silent GREEN.

## 5. Repo hygiene

- `.gitignore` covers `.env`, `*.db`, `data/seed/*.csv` (if large), service-account keys, and `eval/results/` (optional).
- Pre-commit: `ruff`, `mypy` (lenient), `gitleaks`. Never create or download service-account key files; use `gcloud auth application-default login` locally.
