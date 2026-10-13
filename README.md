# PauseGuard: Claude Code Starter Kit

This folder contains everything Claude Code needs to build **PauseGuard** for the **Google Cloud AI Builder Cup 2026**: the product, the contest rules, the architecture, and the phase-by-phase build prompts.

> Phase 11 replaces this README with the real project README.

## What's inside

```
CLAUDE.md                      ← Claude Code reads this automatically: rules, stack, repo layout
PROGRESS.md                    ← phase tracker (Claude updates it)
.env.example                   ← environment variables
.claude/commands/
  next-phase.md                ← /next-phase : runs the next unfinished phase
  check-requirements.md        ← /check-requirements : audits against the contest checklist
docs/
  HACKATHON_REQUIREMENTS.md    ← official submission rules, deadline, deliverables, final checklist
  BRIEF_DESCRIPTION.md         ← required brief description (Firebase, Firestore, Cloud Run, Gemini)
  PRD.md                       ← product requirements, personas, user stories, metrics
  ARCHITECTURE.md              ← Google Cloud architecture, flow, decisions, env vars
  AGENTS_SPEC.md               ← ADK agents, prompts, schemas, deterministic verdict policy
  DATA_SPEC.md                 ← synthetic data, BigQuery/SQLite/Firestore schemas, eval set
  API_SPEC.md                  ← REST endpoints and JSON contracts
  UI_SPEC.md                   ← screens, design system, accessibility
  EVAL_PLAN.md                 ← benchmark method (required "performance report" slide)
  SECURITY_PRIVACY.md          ← prompt-injection defence, PII, IAM, responsible AI
  DEPLOYMENT.md                ← gcloud / Firebase steps, cost table
  DEMO_SCRIPT.md               ← 3–4 minute video, shot by shot
  SUBMISSION_DECK.md           ← content for every slide of the official template
  DECISIONS.md                 ← decision log
prompts/
  phase-00 … phase-11          ← one prompt per build phase
reference/
  Submission_Template_AI_Builder_Cup.pptx   ← the official template
private/                       ← git-ignored: research notes and pitch Q&A prep (not for judges)
```

## How to use it

**⏰ The deadline is ≈ 18 Oct 2026, 18:28 UTC (confirm on the dashboard). Plan to submit by the end of 17 Oct.**

1. **Today:**
   - Install Claude Code, Python 3.12 + `uv`, Node 20+, `gcloud` and `firebase-tools`.
   - Set up a Google Cloud project with billing (or credits) that lasts **past the evaluation period**.
   - Run `gcloud auth application-default login`.
2. Copy this folder to where you want the project, then `cd` into it, run `git init` and start `claude`.
3. Type **`/next-phase`**. Claude reads `PROGRESS.md`, runs the next row, tests it, commits and stops. Review it, then run `/next-phase` again. The rows follow an 8-day plan with a **first deploy on day 4**.
   - If slash commands aren't picked up, paste this: *"Read CLAUDE.md and PROGRESS.md, then execute the next row in PROGRESS.md."*
4. Run **`/check-requirements`** after every row from day 6 onward.

**When you're needed:**
- Day 2: skim the generated scam and legit messages (about 30 min).
- Day 4: GCP project, billing and approval to create resources.
- Day 7: confirm Gemini pricing.
- Day 8: team name, recording the 3–4 minute video, making the repo public, and submitting the deck, video, live link, GitHub link and brief description.

**After submitting:** keep the app, the video and the repo up and public until results are announced. Claude sets up uptime alerts in phase 10, so watch your email.

## Tips for working with Claude Code on this

- Do one phase per session. Start a new session (`/clear`) between phases; CLAUDE.md and PROGRESS.md carry the context forward.
- If Claude goes off-spec, tell it: "Re-read docs/<file>.md and follow it."
- Keep `docs/DECISIONS.md` honest. Judges ask "why", and this file is your answer sheet.
- Never let it commit `.env` or key files. Use Application Default Credentials only.
