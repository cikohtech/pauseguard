# Phase 10: Deploy to Google Cloud (two passes)

**Read first:** `docs/DEPLOYMENT.md` (all of it, especially §7), `docs/SECURITY_PRIVACY.md` §3, `docs/HACKATHON_REQUIREMENTS.md` §0.1.

This phase runs **twice** (see the `PROGRESS.md` rows): **Pass A** on day 4, right after the API works, so a live link exists early, and **Pass B** on day 7 for the final deploy plus the evaluation-period safeguards. Check `PROGRESS.md` to see which pass you're on.

## Pass A: first deploy (day 4)
1. Check the prerequisites with the user: project ID, billing, a budget alert (**alert only, no auto cut-off**), the credit/trial expiry date, and the gcloud + firebase logins. **Ask before running any command that creates billable resources.**
2. Write and run `infra/setup.sh` (idempotent; verify each gcloud flag against the current docs first).
3. `infra/set_analyst_claim.py`, plus create the demo analyst account.
4. `make seed-cloud`, `make deploy-api`, and `make deploy-web` (even if the web is still a placeholder), then `make smoke` against the live API.
5. Confirm that Firebase Hosting, Firebase Auth, Firestore, Cloud Run and Gemini (Vertex AI) are all in use on the live stack, and note it in PROGRESS.md.

## Pass B: final deploy + uptime (day 7)
1. Redeploy the API and web from a clean `main`, then `make smoke`.
2. Re-run the benchmark against the deployed API (`--target cloud`) and update the report.
3. **Evaluation-period safeguards, every item in `DEPLOYMENT.md` §7:**
   - `--min-instances 1`, `--max-instances 5`, `--concurrency 20`
   - Cloud Monitoring uptime checks on the hosting URL and `/healthz`, with an alert policy emailing the user
   - `/healthz` dependency checks; `/admin/selftest`; Cloud Scheduler jobs for the daily selftest and the 6-hourly `/admin/reset-demo`
   - Vertex AI quota checked; backoff on 429
   - Rate limit at 30 checks/hour/IP
4. Check Cloud Logging and Cloud Trace, and screenshot an agent trace for the deck and video.
5. Tag `v1.0-submission` (after phase 11's final commit, re-tag if needed) and note the deployed revision IDs in PROGRESS.md.

## Acceptance
- Pass A: the live URL loads in incognito; the API smoke test passes in the cloud.
- Pass B: all 3 scenarios pass `make smoke` on the live stack; uptime checks are green; the scheduler jobs have run once successfully; the benchmark has been regenerated from cloud results. Commit `phase-10: deployed (pass A|B)`.
