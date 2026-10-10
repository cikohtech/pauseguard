# Phase 09: Benchmark

**Read first:** `docs/EVAL_PLAN.md` (all of it, especially the honesty rules).

## Goal
Real, reproducible numbers for the required "Performance report / Benchmarking" slide.

## Tasks
1. `eval/pricing.yaml`: ask the user to confirm the current Vertex AI price for the model in use (with the source URL and date), or fetch it from the official pricing page if you can. Never guess.
2. `eval/run_benchmark.py` for B0 (rules only), B1 (single Gemini prompt; write it in `eval/baselines/single_prompt.py`) and PauseGuard full, on the **test split**, against the local stack first and then the deployed one (after phase 10, re-run there).
3. `eval/report.py` → `eval/reports/benchmark.md` plus 4 PNG charts (see EVAL_PLAN §5) and the auto-generated headline sentence.
4. Breakdown tables by language, evidence type and age band (fairness).
5. (Optional, skip if behind) The human clarity rating: generate `eval/human_rating_form.md` with 20 explanations, and ask the user to collect the ratings into `eval/human_ratings.csv`. The report includes them when present.

## Acceptance
`make eval` reproduces the report. The numbers are internally consistent. Commit `phase-09: benchmark`.
