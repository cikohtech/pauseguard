# PROGRESS

**Deadline:** prototype submission closes ≈ **18 Oct 2026, 18:28 UTC (≈ 19 Oct, 02:28 Singapore time)**; confirm on the Hack2skill dashboard. **Target: submitted by the end of 17 Oct.** 18 Oct is buffer only.

Claude Code updates this file at the end of every phase: tick the boxes, then add notes, decisions and known issues. `/next-phase` runs the rows **from top to bottom** (the order is deliberate: we deploy early, on day 4, so the live link exists well before the deadline).

| # | Day (target) | Phase | Prompt | Status | Notes |
|---|---|---|---|---|---|
| 1 | Day 1 · 10–11 Oct | 00 Setup | prompts/phase-00-setup.md | ☑ done (10 Oct) | Monorepo scaffold. `make setup/test/lint/dev` pass; `/healthz` ok; landing placeholder at :5173; Docker image builds. Model switched to `gemini-3.8-flash` (2.5 Flash retires 16 Oct); ADK 2.11.0 notes in DECISIONS.md |
| 2 | Day 1 · 11 Oct | 01 Data | prompts/phase-01-data.md | ☑ done (10 Oct) | 500 customers / ~71k txns / 15 scam episodes, deterministic; `make seed-local` 1.6 s from scratch (SQLite + emulator watchlist/personas); `make history` prints Mrs Tan's 90 days. TransactionRepo (SQLite, BigQuery) + one-query `risk_snapshot`; StateRepo (Firestore, memory) with a shared contract suite. BigQuery parity test written, runs at row 7 |
| 3 | Day 2 · 12 Oct | 02 Eval dataset | prompts/phase-02-eval-dataset.md | ☑ done (10 Oct) | 160 cases (80/80), exact DATA_SPEC §4 mix, 5 injection cases, dev 60 / test 100. REVIEW.md approved by the user 10 Oct; 96 PNG + 16 PDF evidence; test split frozen in `eval/TEST_SPLIT_HASH` (`make eval-verify`). Drafts written from the seed prompts (user kept them over a Gemini redraft). Demo files in `data/demo/`. GCP project up, Gemini 3.8 Flash verified |
| 4 | Day 2–3 · 12–13 Oct | 03 Risk + evidence agent | prompts/phase-03-risk-and-evidence.md | ☑ done (11 Oct) | `compute_txn_risk` (one `risk_snapshot` call; the caller passes the watchlist hit) + `rules_only_verdict`; EN/ZH injection pre-scan; PII redaction on every log line. Evidence agent = ADK `LlmAgent` + `output_schema`, own validation, 1 retry, then a fallback with `failed=True`. **Dev split (60): typology 59/60, scams named 30/30, legit false alarms 1/30, p50 4.4 s** (`eval/reports/evidence_dev.md`, `make evidence-dev`). Demo: Tan GOV 0.99 (6 boxed flags), Raj JOB_TASK 0.98 (3 boxed), Aisyah PDF NONE 0.95. CLI: `python -m app.agents.evidence_agent --file … --text …` |
| 5 | Day 3 · 13 Oct | 04 Full agent pipeline | prompts/phase-04-orchestration.md | ☐ todo | |
| 6 | Day 4 · 14 Oct | 05 API | prompts/phase-05-api.md | ☐ todo | |
| 7 | Day 4 · 14 Oct | 10a First deploy (Pass A) | prompts/phase-10-deploy.md | ☐ todo | human: GCP project + billing; live link from now on |
| 8 | Day 5 · 15 Oct | 06 Customer app | prompts/phase-06-customer-app.md | ☐ todo | redeploy web at the end |
| 9 | Day 6 · 16 Oct | 07 Console + landing | prompts/phase-07-console.md | ☐ todo | redeploy at the end |
| 10 | Day 6 · 16 Oct | 08 Hardening (MVP only) | prompts/phase-08-hardening.md | ☐ todo | no stretch features |
| 11 | Day 7 · 16–17 Oct | 09 Benchmark | prompts/phase-09-benchmark.md | ☐ todo | human: confirm the price |
| 12 | Day 7 · 17 Oct | 10b Final deploy + uptime (Pass B) | prompts/phase-10-deploy.md | ☐ todo | min-instances 1, uptime checks, schedulers |
| 13 | Day 8 · 17 Oct | 11 Submission | prompts/phase-11-submission.md | ☐ todo | human: team name, record video, submit |

Status values: ☐ todo · ◐ in progress · ☑ done

**If you fall behind:** cut in this order: the Gemini single-prompt baseline (B1), the dashboard charts (keep the KPI tiles), the console's Watchlist page, the Raj scenario. **Never cut:** a live deploy, the 3 demo personas, the evidence overlay, the benchmark rules-vs-PauseGuard comparison, Firebase + Firestore + Cloud Run + Gemini.

## Known issues

- **Local tools:** Java 21 is installed (`brew install openjdk@21`; it's keg-only, and the Makefile adds it to PATH). firebase-tools runs through a pinned `npx` (the global npm prefix is root-owned), so `make dev` / `make emulators` now start the Firestore + Auth emulators. **GCP (10 Oct):** `gcloud` is installed; project `pauseguard-sg` has billing and ADC; the Vertex AI API is enabled and `gemini-3.8-flash` answers on `global`. Row 7 still runs `infra/setup.sh` (the other APIs, Firestore DB, BigQuery dataset, bucket, service account, secrets).
- The Firestore emulator keeps data in memory. After (re)starting `make dev` or `make emulators`, run `make seed-local` again (about 2 s) so the watchlist and personas are back.
- **Not yet run:** the BigQuery parity test (`uv --directory backend run pytest -m live -k bigquery`) and `make seed-cloud`. Both need the GCP project from row 7. `make seed-cloud` regenerates the data with today's date, so run it again on 17 Oct (row 12) so the 90-day window is fresh for judging.
- `npm audit` reports 7 "high" issues, all in the `shadcn` CLI's build-time tree (micromatch via fast-glob/ts-morph). None of it ships to the browser. Don't run `npm audit fix --force` (it downgrades shadcn); re-check when shadcn publishes a fix.
- Starlette warns that `httpx` in `TestClient` is deprecated in favour of `httpx2`. It's harmless for now.
- **Spec conflict for phase 04 (found in phase 02):** AGENTS_SPEC §4 makes a HIGH `PAY_TO_EARN` flag force RED, but DEMO_SCRIPT (2:10–2:35) and PRD show Raj's job scam as **AMBER**. Raj's demo chat (`data/demo/raj_job_chat.png`) is plainly pay-to-earn. Decide in phase 04 (e.g. keep the RED rule and change the demo beat, or make PAY_TO_EARN force RED only with another HIGH flag) and record it in DECISIONS.md.
- Eval renders use macOS system fonts (PingFang SC). Re-rendering on another OS changes the PNG bytes and breaks `eval/TEST_SPLIT_HASH`; the rendered files are committed, so don't re-render them.
- `/healthz` doesn't check its dependencies yet (Firestore, BigQuery, model); that's planned for phase 10 (DEPLOYMENT §7).
- **For phase 04 (from phase 03):** (1) fusion must treat `EvidenceRun.failed` as "analysis failed" → AMBER + `needs_review`; the fallback `EvidenceAnalysis` itself (UNKNOWN, 0.0, no flags) would otherwise fall through to GREEN. (2) `compute_txn_risk(..., watchlist_hit=...)` expects the caller to look up the payee account (`state.get_watchlist("ACCOUNT", transfer.account_number)`); run it alongside the risk query. (3) The live run confirms Raj's chat gives **PAY_TO_EARN (HIGH)**, so the Raj AMBER/RED spec conflict above must be decided there.
- **Latency:** the evidence agent alone takes p50 4.4–5.0 s and p95 7.3–7.8 s on dev (Tan's 6-flag chat takes 7–8 s with about 870 output tokens). The phase 04 target is p50 ≤ 6 s for the whole pipeline, and the explainer runs after fusion, so it will be tight. Levers for phase 08: `media_resolution`, shorter quotes and summary, fewer entity fields, a per-agent thinking level.
- The injection pre-scan reads the customer's answer, pasted text and the model's **verbatim quotes**. It has no OCR of its own, so injections inside images or PDFs are caught only when the model quotes them (the prompt tells it to). 1 dev false alarm remains: ev_0127, a real friend on a new number (FAKE_FRIEND 0.85).

## Decisions log
See `docs/DECISIONS.md`.
