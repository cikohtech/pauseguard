# Phase 00: Setup & scaffold

**Read first:** `CLAUDE.md`, `docs/HACKATHON_REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `PROGRESS.md`.

## Goal
An empty but runnable monorepo: the backend answers `/healthz`, the web app shows a placeholder landing page, and tests and lint pass.

## Tasks
1. `git init` (if needed), add `.gitignore`, `LICENSE` (MIT), `README.md` (stub), and `.env.example` (copy it from `ARCHITECTURE.md` §5).
2. Create the exact repo layout from `CLAUDE.md`.
3. Backend: `uv init`, then add `fastapi uvicorn[standard] pydantic pydantic-settings google-adk google-genai google-cloud-bigquery google-cloud-firestore google-cloud-storage firebase-admin python-multipart sse-starlette slowapi structlog`, and dev deps `pytest pytest-asyncio httpx ruff mypy`. Add `app/config.py` (every env var), `app/main.py` with `/healthz`, CORS, structured JSON logging, and `app/models/schemas.py` containing **all** the Pydantic models and enums from `docs/AGENTS_SPEC.md` and `docs/API_SPEC.md`.
4. Check the installed ADK version and its docs. Write a 10-line note in `docs/DECISIONS.md` covering the ADK version, the import paths you'll use, whether `output_schema` and tools can be combined, and how to call `google_search`.
5. Check the current GA Gemini Flash model ID on Vertex AI. Put it in `.env.example` and in DECISIONS.md with the date.
6. Web: Vite + React + TS, Tailwind, shadcn/ui init, React Router with routes `/`, `/app/*`, `/console/*`, plus i18next with `en` and `zh` stubs and Vitest.
7. A `Makefile` with the targets listed in `CLAUDE.md`. `make dev` runs the API (port 8000) and web (5173) together, plus the Firestore emulator if it's installed.
8. A pre-commit config (ruff, gitleaks).
9. A smoke test, `tests/test_health.py`.

## Acceptance
- `make setup && make test && make lint` pass. `make dev` → http://localhost:5173 shows the landing placeholder, and http://localhost:8000/healthz returns ok.
- `schemas.py` matches the specs. DECISIONS.md is filled in.
- PROGRESS.md is updated, and the commit is `phase-00: scaffold`.
