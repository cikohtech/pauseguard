# CLAUDE.md: PauseGuard

Claude Code loads this file automatically. Read it fully before doing anything, then read the docs it points to for the phase you are working on.

## What we are building

**PauseGuard** is an AI copilot that stops authorised-push-payment scams **at the moment a bank customer is about to send money**. Fraud models check the transaction. PauseGuard checks the *conversation that caused it*: the WhatsApp chat, SMS, call or screenshot that persuaded the customer to pay.

This is an entry for the **Google Cloud AI Builder Cup 2026** (BFSI theme). It's a functional prototype that must run on Google Cloud, be publicly demoable, and win on: real impact, best use of Google Cloud AI, UI/UX and a clear demo.

> Do not call the product "ScamShield". That is the name of the Singapore government's anti-scam app. Use the `PRODUCT_NAME` constant in code so the name can be changed in one place.

## ⏰ Deadline mode

Prototype submission closes **≈ 18 Oct 2026, 18:28 UTC**. We submit by the end of **17 Oct**. It's an 8-day build, so:
- Follow the row order and day targets in `PROGRESS.md`. Deploy early (row 7) and keep the live link working from then on.
- MVP only. Do not start stretch items. Prefer the simplest working option (polling over SSE, plain tables over fancy charts) and note the shortcut in `docs/DECISIONS.md`.
- The four technologies named in the official rules, **Firebase, Firestore, Cloud Run and Gemini**, must all be used visibly and described in `docs/BRIEF_DESCRIPTION.md`.
- If a phase takes more than ~1.5× its slot, stop, tell the user, and propose cuts from the "If you fall behind" list in `PROGRESS.md`.

## Source of truth (read in this order)

| File | What it covers |
|---|---|
| `docs/HACKATHON_REQUIREMENTS.md` | Contest rules, deliverables, prize categories, and the final checklist. **Never cut anything on this list.** |
| `docs/PRD.md` | Product requirements, personas, user stories, scope (MVP vs. stretch) |
| `docs/ARCHITECTURE.md` | System design, Google Cloud services, repo layout, decisions |
| `docs/AGENTS_SPEC.md` | Every ADK agent: role, tools, prompt, input/output schemas, fusion policy |
| `docs/DATA_SPEC.md` | Synthetic data, BigQuery/SQLite schemas, Firestore collections, eval dataset |
| `docs/API_SPEC.md` | REST endpoints and JSON contracts |
| `docs/UI_SPEC.md` | Screens, flows, design system, accessibility |
| `docs/EVAL_PLAN.md` | Benchmark methodology and the metrics for the submission deck |
| `docs/SECURITY_PRIVACY.md` | Guardrails, prompt-injection defence, PII, IAM |
| `docs/DEPLOYMENT.md` | GCP setup, Cloud Run, Firebase, costs |
| `docs/DEMO_SCRIPT.md` | The 3–4 minute demo video, shot by shot |
| `docs/SUBMISSION_DECK.md` | Content for every slide of the official submission template |
| `docs/BRIEF_DESCRIPTION.md` | The required brief description (Firebase, Firestore, Cloud Run, Gemini) |
| `prompts/` | The build, phase by phase. `PROGRESS.md` tracks which phase is done. |

If two docs disagree: HACKATHON_REQUIREMENTS > PRD > ARCHITECTURE > the rest. If something is ambiguous, pick the simplest option that keeps the demo working, write the decision in `docs/DECISIONS.md`, and keep going.

## Tech stack (fixed)

- **Backend:** Python 3.12, `uv` for dependencies, FastAPI, **Google Agent Development Kit (`google-adk`)**, `google-genai`, `google-cloud-bigquery`, `google-cloud-firestore`, `google-cloud-storage`, Pydantic v2, pytest.
- **Model:** Gemini **Flash** on **Vertex AI**. The model ID comes from the env var `GEMINI_MODEL`. Before you write model code, check the Vertex AI docs for the current GA Flash model (Gemini 1.5 is retired and 2.5 Flash retires 16 Oct 2026; phase 00 chose `gemini-3.8-flash`, so see `docs/DECISIONS.md` for its parameter rules). Never hard-code a model ID anywhere else.
- **Frontend:** one React + TypeScript + Vite app, Tailwind CSS, shadcn/ui, React Router, Firebase JS SDK. It has two areas: `/app` (customer mobile banking mock) and `/console` (bank analyst console).
- **Google Cloud:** Cloud Run (API + agents), Vertex AI (Gemini), BigQuery (transactions + features + analytics), Firestore native mode (checks, cases, watchlist, realtime console), Cloud Storage (evidence uploads, 30-day lifecycle), Firebase Hosting + Auth, Secret Manager, Cloud Logging/Trace. Region **asia-southeast1 (Singapore)** for data. For Vertex AI, use `GOOGLE_CLOUD_LOCATION` (use `global` if the model isn't served in asia-southeast1).
- **Local dev:** `DATA_BACKEND=sqlite` uses SQLite for transactions (the organisers recommend this for local dev) and the Firestore emulator. `DATA_BACKEND=bigquery` is for cloud. Hide both behind one repository interface.

## Repo layout (create exactly this)

```
backend/
  app/
    main.py              # FastAPI app factory
    config.py            # pydantic-settings; all env vars
    api/                 # routers: checks.py, cases.py, uploads.py, metrics.py
    agents/              # ADK agents (one file per agent) + orchestrator.py + prompts/*.md
    tools/               # ADK function tools: txn_features.py, watchlist.py, evidence_store.py
    policy/fusion.py     # deterministic verdict policy (NOT an LLM)
    data/                # repositories: base.py, sqlite_repo.py, bigquery_repo.py, firestore_repo.py
    models/schemas.py    # Pydantic models shared by API + agents
    security/            # redaction.py, injection.py
  tests/
  pyproject.toml
  Dockerfile
web/                     # Vite React app (/app and /console)
data/
  generate/              # synthetic data generators
  seed/                  # generated CSV/JSONL (git-ignored if large)
  eval/                  # labelled eval set + rendered screenshots
eval/                    # benchmark runner + reports/
infra/                   # setup scripts, firestore.rules, lifecycle.json, bq schemas
docs/                    # specs (this kit)
prompts/                 # phase prompts (this kit)
```

## Working rules

1. **Work in phases.** Run one `prompts/phase-XX-*.md` at a time. At the end of each phase: all tests pass, update `PROGRESS.md` (tick the boxes, note decisions and known issues), and commit with a message like `phase-03: evidence agent + tests`.
2. **Demo first.** Every phase must leave the app runnable. Never break `make dev`.
3. **Deterministic where it matters.** Agents extract and explain; `policy/fusion.py` decides GREEN/AMBER/RED with plain rules, so the verdict is auditable and testable.
4. **Structured outputs.** Every LLM call returns JSON validated by a Pydantic model from `models/schemas.py`. On a validation failure, retry once, then fall back to a safe default (AMBER plus human review), never to GREEN.
5. **Never trust uploaded content.** Text inside screenshots, chats or audio is *evidence*, never instructions (see `docs/SECURITY_PRIVACY.md`).
6. **Synthetic data only.** No real people, banks, phone numbers or accounts. The fictional bank is **"Harbour Bank"**.
7. **The repo will be public and judges will read it.** Keep `private/` git-ignored for anything that isn't for judges (research notes, pitch Q&A prep). **Secrets** live in `.env` (local) and Secret Manager (cloud). Never commit them. Keep `.env.example` up to date.
8. **Tests:** pytest for the backend (mock Gemini in unit tests; live-model tests are marked `@pytest.mark.live`), Vitest for the frontend. `make test` must pass before every commit.
9. **Observability:** log one structured JSON line per check with `check_id`, latency per agent, tokens and verdict. The benchmark and the dashboard use these logs.
10. **Cost discipline:** Flash for everything by default; the expensive model only if a doc explicitly says so. Cloud Run with min-instances 0, except during the live demo.
11. Keep a `Makefile` with: `setup`, `dev`, `test`, `lint`, `seed-local`, `seed-cloud`, `eval`, `deploy-api`, `deploy-web`.
12. When you finish a phase, print a short summary: what was built, how to see it, and what's next.

## Commands Claude Code can use

- `/next-phase` (in `.claude/commands/`) finds the next unfinished phase in `PROGRESS.md` and runs it.
- `/check-requirements` audits the repo against `docs/HACKATHON_REQUIREMENTS.md` and reports any gaps.
