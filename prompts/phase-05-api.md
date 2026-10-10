# Phase 05: API & persistence

**Read first:** `docs/API_SPEC.md`, `docs/DATA_SPEC.md` §3, `docs/SECURITY_PRIVACY.md` §3.

## Goal
Every endpoint in API_SPEC works against the emulator and SQLite, and is documented in OpenAPI.

## Tasks
1. Routers: `checks.py` (create, message, get, events via SSE, choice, feedback), `uploads.py` (signed URLs; locally, a direct multipart fallback that saves to `./.local_uploads`), `cases.py` (list, get, decision, plus watchlist upsert on REPORT_SCAM), `metrics.py`, and `admin.py` (reset-demo).
2. Firebase ID-token verification as a dependency, with analyst-role checks. Locally, allow `AUTH_DISABLED=true` for development only, which must never be set in cloud (assert at startup when `K_SERVICE` is set).
3. Stream a row per check into `checks_analytics` (BigQuery in cloud, a SQLite table locally).
4. Rate limiting (slowapi) on `/checks`.
5. Consistent error envelope; analysis timeout → AMBER response, not an error.
6. API tests with httpx for every endpoint (mock the orchestrator), plus one end-to-end test marked `live`.

## Acceptance
`make dev`, then the curl scripts in `scripts/demo_curl.sh` run the 3 scenarios end to end. `/docs` is complete. Commit `phase-05: api`.
