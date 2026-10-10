# Phase 03: Transaction risk tool & Evidence agent

**Read first:** `docs/AGENTS_SPEC.md` §0–2, `docs/SECURITY_PRIVACY.md` §1.

## Goal
The two core signal sources work and are tested in isolation.

## Tasks
1. `tools/txn_features.py::compute_txn_risk`: implement the exact points table and the rules-only baseline function `rules_only_verdict(score)`. It must be pure and fast (one repo call). Unit-test every feature and the cap at 100.
2. `security/injection.py` pre-scan (EN + ZH patterns) and `security/redaction.py`, with tests.
3. `agents/evidence_agent.py` plus `agents/prompts/evidence.md` (use the prompt core from the spec): multimodal input from GCS URIs or local paths (local dev), JSON output validated by `EvidenceAnalysis`, one retry on validation failure, then a safe fallback.
4. `box_2d` handling: validate the range 0–1000 and drop invalid boxes.
5. A CLI, `python -m app.agents.evidence_agent --file data/demo/tan_mas_chat.png --text "..."`, that prints the JSON.
6. Run it on the **dev split only** (about 30 cases). Print typology accuracy and look at the failures. Iterate on the prompt (keep a changelog at the top of the prompt file).

## Acceptance
Unit tests pass with mocked Gemini. A live run on the demo images gives the expected typology and at least 3 correct flags with sensible boxes. Commit `phase-03: risk tool + evidence agent`.
