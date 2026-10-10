# Phase 07: Analyst console (/console) & dashboard

**Read first:** `docs/UI_SPEC.md` Area 2, `docs/PRD.md` §4 analyst stories.

## Goal
A realtime console that makes the "bank side" of the story compelling.

## Tasks
1. Analyst login (Firebase email/password; the emulator locally) and a route guard.
2. Queue with a Firestore realtime listener (RED first), and the new-case highlight animation.
3. Case view tabs: Summary, Evidence (reuse the evidence card plus entity chips), Transaction risk (gauge, feature table, 90-day chart with the spike highlighted), Intel, Audit.
4. Sticky action bar with keyboard shortcuts R/H/E/S, a note, a confirm toast, and the watchlist update toast on Report.
5. Dashboard (`/console/dashboard`): KPI tiles plus 3 charts (Recharts) from `/metrics`.
6. Watchlist page.
7. Landing page `/` from UI_SPEC Area 3.

8. At the end, run `make deploy-api deploy-web` and smoke-test the live link.

## Acceptance
Two browser windows side by side: submit Mrs Tan's transfer in `/app` → the case appears in `/console` within 1 s of the verdict → Report → the watchlist updates. Commit `phase-07: console + dashboard + landing`.
