# Evaluation Plan: PauseGuard

This plan produces the **"Prototype Performance report / Benchmarking"** slide, which is required by the submission template.

## 1. Questions we answer

1. Does adding conversation evidence catch more scams than transaction rules alone? (headline)
2. How often do we wrongly stop legitimate payments?
3. Do we name the right scam type?
4. Is it fast and cheap enough for a real payment flow?
5. Do people understand the explanations?

## 2. Systems compared

| System | Description |
|---|---|
| **B0 Rules-only** | `compute_txn_risk` thresholds only (RED ≥ 70, AMBER ≥ 40) |
| **B1 Gemini single-prompt** | One Gemini call with all inputs, which outputs the verdict directly (no agents, no fusion). Shows the value of the agent design. |
| **PauseGuard (full)** | Agents + intel + deterministic fusion |
| (optional) **No-evidence ablation** | PauseGuard with evidence removed, i.e. only the customer's text answer |

## 3. Dataset

`data/eval/cases.jsonl` (see `DATA_SPEC.md` §4): 160 cases, a **dev split of 60** for tuning prompts and thresholds, and a **test split of 100 that is reported and never tuned on**. Freeze the test split by committing a SHA-256 of the file in `eval/TEST_SPLIT_HASH`.

## 4. Metrics

Treat SCAM as positive and "stopped" as verdict ∈ {AMBER, RED}.
- **Scam recall** = scams stopped ÷ scams
- **Hard-stop recall** = scams marked RED ÷ scams
- **False-positive rate** = legit stopped ÷ legit (report both the AMBER and RED rates; legit→RED is the costly one)
- **Precision** and **F1**
- **Typology accuracy** on scams (exact match)
- **Latency**: p50 and p95 end to end per case, plus per agent
- **Cost per check**: tokens in/out × the current Vertex AI price for the model (read prices from `eval/pricing.yaml`, filled in by hand with the date and source URL; never invent prices)
- **Explanation clarity** (optional if time is short): 20 random AMBER/RED explanations, rated 1–5 by 3–5 people (friends/family; include someone 60+). Use a Google Form, and save the results to `eval/human_ratings.csv`.
- Breakdowns by language and by evidence type (image / text / PDF / none).

## 5. Runner (`eval/run_benchmark.py`)

- Calls the **deployed** API (or the in-process orchestrator with `--local`) for every case. Concurrency 4. Retries on 429 with backoff.
- Saves the raw results to `eval/results/<date>_<system>.jsonl` with the model ID, git SHA and timestamp.
- `eval/report.py` writes `eval/reports/benchmark.md` and PNG charts:
  1. Grouped bar: recall and FPR for B0 / B1 / PauseGuard
  2. Confusion matrix (verdict × label)
  3. Latency histogram with p50/p95 lines
  4. Typology confusion heatmap
- The headline sentence is generated from the numbers, e.g. "Rules alone stopped 41% of scams; PauseGuard stopped 93% with a 4% false-positive rate, in 3.8 s median at US$0.004 per check."

## 6. Honesty rules

- Report the test split only, with dates and model ID.
- Don't tune on test. If you must change prompts after seeing test results, create a **new** test split (re-generate) and say so in the report.
- Note the limitations in the report: synthetic data, our own labels, a small sample, no real bank traffic.
