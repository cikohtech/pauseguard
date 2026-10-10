# Phase 06: Customer app (/app)

**Read first:** `docs/UI_SPEC.md` (design system + Area 1), `docs/PRD.md` §4 customer stories.

## Goal
A polished mobile banking mock with the full PauseGuard check-in experience. This is the screen judges remember.

## Tasks
1. Design tokens (Tailwind theme + CSS variables, light and dark), fonts (Inter + Noto Sans SC), and the phone frame layout.
2. Screens 1–7 from UI_SPEC Area 1: persona picker, home, transfer form (with a "Prefill demo scenario" link), review, check-in bottom sheet with quick replies and upload, analysing step-ticks (polling is fine), and the GREEN/AMBER/RED verdict screens.
3. **Evidence card component:** shows the image with numbered flag boxes converted from `box_2d` (0–1000, [ymin,xmin,ymax,xmax]) to absolutely positioned percentage boxes, and a matching numbered list. It must be responsive and accessible (each box has an aria-label).
4. AMBER confirm dialog, trusted-contact `tel:` link, 1799 link, feedback thumbs.
5. Every string in i18n (en, zh). The language follows the persona, and the header toggle switches it.
6. Vitest tests for the evidence card box maths and the verdict screen rendering.
7. Accessibility pass: keyboard, focus, contrast (check with axe in a Playwright test).

8. At the end, run `make deploy-web` so the live link shows the new app.

## Acceptance
All 3 scenarios can be clicked through locally with real agents. Screenshots look like a real bank app. Axe reports no serious issues. Commit `phase-06: customer app`.
