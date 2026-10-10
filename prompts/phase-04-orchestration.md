# Phase 04: Intel, fusion, explainer, case file & orchestrator

**Read first:** `docs/AGENTS_SPEC.md` §3–8, `docs/ARCHITECTURE.md` §2.

## Goal
A complete analysis pipeline callable as `await run_check(...)`.

## Tasks
1. `tools/watchlist.py` (normalise phone, URL, domain and account; look them up in Firestore).
2. `agents/search_agent.py` (google_search only) and `agents/intel_agent.py` (watchlist tool + `AgentTool(search_agent)`, max 2 searches, unknown entities only).
3. `policy/fusion.py`: the exact rules from the spec, with thresholds in config. **100% branch coverage** in its tests.
4. `agents/explainer_agent.py` (en + zh, the tone rules, word limits enforced in post-processing) and the GREEN template.
5. `agents/casefile_agent.py`.
6. `agents/orchestrator.py`: the flow from AGENTS_SPEC §7, with parallel evidence + intel, a total timeout → AMBER + needs_review, and per-agent latency and token accounting, plus emitting progress events through a callback (used by SSE later).
7. ADK eval sets: 3 golden cases per agent in `backend/tests/agent_evals/`.
8. A CLI, `python -m app.agents.orchestrator --scenario tan|raj|aisyah`, that prints the verdict, the customer message (in the persona's language) and the case file.

## Acceptance
The three demo scenarios give RED, AMBER-or-RED and GREEN. p50 latency on the scenarios is ≤ 6 s locally. Tests pass. Commit `phase-04: full agent pipeline`.
