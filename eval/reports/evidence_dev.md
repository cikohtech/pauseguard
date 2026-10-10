# Evidence agent: dev split

Phase 03 tuning run of the evidence agent alone, on the **dev split only** (the test split is never used for tuning; EVAL_PLAN §3). Produced by `eval/evidence_dev.py`.

Model `gemini-3.8-flash` (thinking LOW, media MEDIUM), prompt v3 (2026-10-11, phase 04, latency), 20261010T195019Z, wall 46 s. Raw runs: `eval/results/evidence_dev_20261010T195019Z.jsonl` (git-ignored).

- Cases: 60 (dev split only; 30 scam, 30 legit)
- **Typology accuracy (exact): 59/60 (98%)**
- Scams given a scam typology: 30/30 (100%)
- Legit given NONE: 29/30 (97%)
- Evidence-only stop, scams: 30/30 (100%)
- Evidence-only stop, legit (false alarms): 1/30 (3%)
- Injection detected: 1/1 (100%); false injection hits: 0
- Model failures (fallback): 0
- Flags with a box: 66
- Latency p50 3938 ms, p95 7450 ms; tokens in/out (mean) 3217/425

| Expected typology | Correct |
|---|---|
| BEC_INVOICE | 1/1 (100%) |
| ECOMMERCE | 3/3 (100%) |
| FAKE_FRIEND | 3/3 (100%) |
| GOV_OFFICIAL_IMPERSONATION | 6/6 (100%) |
| INVESTMENT | 6/6 (100%) |
| JOB_TASK | 6/6 (100%) |
| NONE | 29/30 (97%) |
| PHISHING | 4/4 (100%) |
| ROMANCE | 1/1 (100%) |

| Case | Label | Lang | Evidence | Expected | Got (conf) | Flags |
|---|---|---|---|---|---|---|
| ev_0127 | LEGIT | en | image | NONE | FAKE_FRIEND (0.85) | NEW_NUMBER_FRIEND:M, URGENCY:M |
