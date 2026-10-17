# Costs: PauseGuard

Two numbers for the deck: what the **prototype** costs to keep live during judging, and what a **pilot** at one bank (50,000 checks a month) would cost. Every usage figure below is **measured** on the live stack, and every price is copied from Google's published price pages (retrieved 17 Oct 2026, USD, the list price with no discounts). Anything that is an assumption says so.

## 1. What one check uses (measured)

Source: the deployed benchmark run `20261016T1447Z_api_test` (100 test cases through Cloud Run, 16 Oct 2026) and the API's own log lines for the same window (`check_done`, `intel_investigated`; 103 checks), plus BigQuery's job history (`INFORMATION_SCHEMA.JOBS`).

| Resource | Per check (mean over all checks) | Notes |
|---|---|---|
| Gemini input tokens | **5,216** | evidence 2,850 · Scam-Intel 1,185 · case file 804 · explainer 355 |
| Gemini output tokens (thinking included) | **831** | evidence 384 · Scam-Intel 185 · case file 228 · explainer 31 |
| Google Search grounding queries | **2.78** | only the Scam-Intel agent, only on AMBER/RED checks (40 of 103), 7.2 queries per run |
| BigQuery bytes billed | **53 MB** | ~3 small queries (risk snapshot, payee, customer), each billed at BigQuery's 10 MB-per-table minimum; the bytes actually read are 0.35 MB per query |
| Cloud Run time | ~8 s on the customer's path + up to 25 s in the background (case file, web search) | instance-based billing (CPU always allocated), so cost follows instance lifetime, not requests |
| Firestore | not measured per check; we assume ≤ 50 reads + 20 writes | check doc and status updates, watchlist lookups, case, audit, analytics snapshot |
| Cloud Storage | one upload of 0.1–1 MB, deleted after 30 days | |

The benchmark mix is 50% scams, so AMBER/RED checks (and with them the case file and the web search) are far more common than in real traffic. Per-check numbers here are therefore on the **high** side.

## 2. Prices used

| Service | Price (list, USD) | Source |
|---|---|---|
| Gemini 3.8 Flash, Vertex AI Standard tier, global endpoint | $0.75 / 1M input, $3.75 / 1M output tokens (introductory until 31 Dec 2026); **from 1 Jan 2027 $1.50 / $7.50** | https://cloud.google.com/vertex-ai/generative-ai/pricing (retrieved 15 Oct; `eval/pricing.yaml`) |
| Grounding with Google Search (Gemini 3) | 5,000 queries/month free, then **$14 per 1,000 queries** | same page |
| Cloud Run, instance-based billing, asia-southeast1 (Tier 2) | $0.0000216 per vCPU-second, $0.0000024 per GiB-second; free tier 240,000 vCPU-s + 450,000 GiB-s a month (per billing account, at Tier 1 prices) | https://cloud.google.com/run/pricing |
| BigQuery on-demand queries, asia-southeast1 | first 1 TiB/month free, then **$8.4375 per TiB** | https://cloud.google.com/bigquery/pricing |
| Firestore Standard edition, asia-southeast1 | $0.0369 / 100k reads, $0.1107 / 100k writes, $0.0123 / 100k deletes, $0.1846 / GiB-month; free 50k reads, 20k writes, 20k deletes a day, 1 GiB | https://cloud.google.com/firestore/pricing |
| Cloud Storage, Standard class | $0.020–0.026 per GiB-month in every region listed | https://cloud.google.com/storage/pricing |
| Cloud Scheduler | 3 jobs free per billing account, then $0.10 per job per month | https://cloud.google.com/scheduler/pricing |
| Secret Manager | 6 active versions and 10,000 accesses a month free | https://cloud.google.com/secret-manager/pricing |

## 3. Prototype (what judging costs us)

The live demo runs with **min instances 0** (the team's cost decision, DECISIONS 2026-10-16), a web uptime check, a 6-hourly demo reset and a daily self-test. Cloud Monitoring shows 0.25–3.4 billable instance-hours a day for the API between 11 and 16 Oct.

| Item | Assumption | Per month |
|---|---|---|
| Gemini | 30 checks a day by judges and the team × $0.0070 | ≈ $6.30 |
| Google Search grounding | ≈ 2,500 queries, inside the 5,000 free | $0 |
| Cloud Run | 2.5 instance-hours a day × 1 vCPU + 1 GiB = $6.57, minus the free tier (shared with the billing account's other projects) | $1–7 |
| BigQuery, Firestore, Storage, Secret Manager, Logging, Hosting | inside the free tiers | $0 |
| Cloud Scheduler | 2 jobs (free if the billing account has none of its 3 free jobs in use) | ≤ $0.20 |
| **Total** | | **≈ US$8–14 a month** |

For the video recording or a live pitch, `make deploy-api MIN_INSTANCES=1` keeps one warm instance: **$2.07 a day** in Singapore (86,400 s × ($0.0000216 + $0.0000024)). DEPLOYMENT.md's earlier "≈ US$1.7/day" used the Tier 1 price; Singapore is Tier 2.

## 4. Pilot: one bank, 50,000 checks a month

A "check" is a transfer that reached PauseGuard's check-in (risky enough to ask), not every payment the bank processes. Same model, same architecture, Singapore region, the measured per-check usage from §1.

| Item | Calculation | Per month (intro price, 2026) | From 2027 (list price) |
|---|---|---|---|
| Gemini 3.8 Flash | 50,000 × (5,216 in + 831 out tokens) | **$351** | $703 |
| Google Search grounding | 50,000 × 2.78 = 139,000 queries − 5,000 free, × $14 / 1,000 | **$1,874** | $1,874 |
| Cloud Run | 1 always-warm instance (min 1, 1 vCPU / 1 GiB) is enough for ~70 checks an hour; $63.04 − free tier. Two instances for redundancy: $121 | $58–121 | $58–121 |
| BigQuery | 50,000 × 53 MB = 2.43 TiB − 1 TiB free, × $8.4375 | $12 | $12 |
| Firestore | ≤ 2.5M reads + 1M writes, minus the daily free quota | ≈ $1 | ≈ $1 |
| Cloud Storage, Scheduler, Secret Manager, Logging | evidence kept ≤ 30 days (~15 GiB) | ≈ $1 | ≈ $1 |
| **Total** | | **≈ US$2,300–2,360** | ≈ US$2,650–2,710 |
| **Per check** | | **≈ US$0.046** | ≈ US$0.053 |

**Where the money goes:** about 80% is the Scam-Intel agent's Google Search grounding, not Gemini tokens (US$0.0070 per check) or infrastructure. It runs only on AMBER/RED checks and never changes the verdict (it enriches the analyst's case file), so it is the obvious place to save, with three changes that are **not built yet**:
- skip the web search when the watchlist already matched the payee, number or link (it is already a hard stop);
- cache results per domain or platform name for 24 hours (scam campaigns reuse the same sites);
- cap the search agent at 2 queries per check.

At one query per check, grounding drops to $630 a month and the pilot to **≈ US$1,050 (≈ US$0.021 per check)**. In a real bank's traffic far fewer checks are AMBER/RED than in our 50/50 benchmark, which lowers both the grounding and the case-file cost further.

## 5. Is it worth it?

The Singapore Police Force reports a **median loss of S$1,644 per scam case in 2025** (S$913.1M across 41,974 cases; https://www.police.gov.sg/media-hub/police-life/2026/02/scams-and-cybercrime-fell-by-almost-a-quarter-in-2025). At S$1.30 per US$ (an approximate exchange rate, not a price), that is about US$1,265:

- **One stopped median scam pays for ≈ 27,500 checks** at the pilot's all-in US$0.046 per check, or ≈ 180,000 checks counting Gemini tokens only.
- At 50,000 checks a month, the pilot pays for itself if it stops **about two median scams a month**. On our test set it stopped 50 of 50 scams; real-world recall will be lower, and the base rate of scams among checked transfers is the number a pilot must measure.

## 6. How to re-measure

- Tokens, latency and cost per check: `make eval API=deployed`, then `eval/reports/benchmark.md` (prices in `eval/pricing.yaml`).
- Per-agent tokens and grounding queries: Cloud Logging, `jsonPayload.message="check_done"` and `"intel_investigated"` for the API service.
- BigQuery bytes billed: `region-asia-southeast1.INFORMATION_SCHEMA.JOBS_BY_PROJECT`, grouped by `user_email`.
- Cloud Run instance time: Cloud Monitoring metric `run.googleapis.com/container/billable_instance_time`.
