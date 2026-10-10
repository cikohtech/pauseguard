---
description: Run the next unfinished build phase from PROGRESS.md
---
1. Read `CLAUDE.md` and `PROGRESS.md`.
2. Find the first row (top to bottom) whose status is not ☑ done. If one is ◐ in progress, resume it. For phase 10, check whether this row is Pass A or Pass B.
3. Read that row's prompt file in `prompts/`, and every doc it lists under "Read first".
4. Before writing code, give a short plan (5–10 bullets) of what you'll do in this phase.
5. Execute the phase. Run tests often. Ask the user only when the prompt says to, or when an action creates billable cloud resources.
6. Check every acceptance criterion and show the evidence (test output, a command result, a screenshot path).
7. Update `PROGRESS.md` (status, notes, known issues) and `docs/DECISIONS.md`, then commit with the message given in the prompt.
8. End with: what was built, how to see it, what the user must do (if anything), and the next phase.
$ARGUMENTS
