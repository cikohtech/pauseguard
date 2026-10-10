# Phase 11: Submission package

**Read first:** `docs/HACKATHON_REQUIREMENTS.md` (§1 and §5), `docs/SUBMISSION_DECK.md`, `docs/DEMO_SCRIPT.md`.

## Goal
Every deliverable the organisers ask for is ready and consistent.

## Tasks
1. **README.md** (it's what judges read): a one-paragraph pitch, a GIF of the demo, the live link and demo logins, the problem stat with its source, an architecture image, a "Google Cloud services used, and why" table, the agent design, the benchmark headline + table, local setup (`make setup && make seed-local && make dev`), deploy steps, a responsible-AI section, limitations, the team, and the licence.
2. Diagrams: render the Mermaid diagrams to `docs/img/architecture.png` and `docs/img/process-flow.png` (mermaid-cli).
3. Screenshots: use Playwright scripts to capture the 6 screens in UI_SPEC "Wireframes for the deck" from the **deployed** app, saving them to `docs/img/screens/`.
4. `docs/COSTS.md`: prototype and pilot costs from measured tokens per check and the confirmed prices.
5. Fill in `docs/SUBMISSION_DECK.md` with the real numbers. Then generate `submission/PauseGuard_Submission.pptx` **from the official template** in `reference/`: open it with python-pptx, keep its slide order and titles, insert our text and images into each slide, and don't restyle the template. Ask the user for the team name and leader name.
6. Polish `docs/DEMO_SCRIPT.md` with the real numbers (the video must be **3:00–4:00**, target 3:30, showing the live product working). Generate the caption file `submission/captions.srt` from the voice-over, and write a scene-by-scene recording checklist for the user.
7. Fill in `docs/BRIEF_DESCRIPTION.md` with the real numbers and make sure it clearly explains how **Firebase, Firestore, Cloud Run and Gemini** are used. Save the final text as `submission/brief_description.txt`.
8. Run the full audit in HACKATHON_REQUIREMENTS §5 and report every unticked item to the user, along with what they must do themselves (record the video, upload it, make the repo public, submit on the portal).
9. **Public-repo cleanup** (judges will read the repo): move `reference/idea-research.md`, `reference/concept-deep-dive.md` and the "Likely judge questions" section of `docs/SUBMISSION_DECK.md` into a git-ignored `private/` folder, and remove them from git history if they were ever committed (`git filter-repo`, after asking the user). Keep `CLAUDE.md`, `docs/`, `prompts/`, `PROGRESS.md` and the official template; they show how the project was planned. Make sure the README explains in one line that `docs/` holds the design specs, and that it gives the demo logins.
10. Secret scan of the full git history (`gitleaks detect`).
11. Write `submission/SUBMIT_CHECKLIST.md`: the four links (deck file, video, live prototype, GitHub) + the brief description, each with an "opened in incognito ✓" box, and a reminder that everything must stay up and public until results are announced.
12. Tag `v1.0-submission`.

## Acceptance
The deck pptx is generated and the user has reviewed it; the README is complete; the audit list is all ticked except items that only the human can do, which are listed clearly. Commit `phase-11: submission package`.
