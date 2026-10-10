# PROGRESS

**Deadline:** prototype submission closes ≈ **18 Oct 2026, 18:28 UTC (≈ 19 Oct, 02:28 Singapore time)**; confirm on the Hack2skill dashboard. **Target: submitted by the end of 17 Oct.** 18 Oct is buffer only.

Claude Code updates this file at the end of every phase: tick the boxes, then add notes, decisions and known issues. `/next-phase` runs the rows **from top to bottom** (the order is deliberate: we deploy early, on day 4, so the live link exists well before the deadline).

| # | Day (target) | Phase | Prompt | Status | Notes |
|---|---|---|---|---|---|
| 1 | Day 1 · 10–11 Oct | 00 Setup | prompts/phase-00-setup.md | ☑ done (10 Oct) | Monorepo scaffold. `make setup/test/lint/dev` pass; `/healthz` ok; landing placeholder at :5173; Docker image builds. Model switched to `gemini-3.8-flash` (2.5 Flash retires 16 Oct); ADK 2.11.0 notes in DECISIONS.md |
| 2 | Day 1 · 11 Oct | 01 Data | prompts/phase-01-data.md | ☐ todo | |
| 3 | Day 2 · 12 Oct | 02 Eval dataset | prompts/phase-02-eval-dataset.md | ☐ todo | human: review REVIEW.md the same day |
| 4 | Day 2–3 · 12–13 Oct | 03 Risk + evidence agent | prompts/phase-03-risk-and-evidence.md | ☐ todo | |
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

- **Local tools still missing (needed by phase 01 / phase 10):** `firebase-tools` (`npm i -g firebase-tools`), a Java 11+ runtime for the Firestore emulator (`brew install openjdk@21`), and `gcloud` (`brew install --cask google-cloud-sdk`). `make dev` skips the emulator until firebase-tools and Java are installed.
- `npm audit` reports 7 "high" issues, all in the `shadcn` CLI's build-time tree (micromatch via fast-glob/ts-morph). None of it ships to the browser. Don't run `npm audit fix --force` (it downgrades shadcn); re-check when shadcn publishes a fix.
- Starlette warns that `httpx` in `TestClient` is deprecated in favour of `httpx2`. It's harmless for now.
- `/healthz` doesn't check its dependencies yet (Firestore, BigQuery, model); that's planned for phase 10 (DEPLOYMENT §7).

## Decisions log
See `docs/DECISIONS.md`.
