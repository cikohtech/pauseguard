# Phase 08: Guardrails, polish & stretch features

**Read first:** `docs/SECURITY_PRIVACY.md`, `docs/HACKATHON_REQUIREMENTS.md` §2–3.

## Goal
Make it robust and safe enough for a public demo, then add the stretch features judges notice.

## Tasks (deadline mode: do 1–5 only; items 6–8 are post-submission ideas)
1. Firestore rules (`infra/firestore.rules`) plus rules tests in the emulator.
2. GCS lifecycle and CORS JSON, a consent line in the check-in sheet, PII redaction applied to all logs.
3. Failure drills: kill Gemini (bad model ID), slow network, a 10 MB image, an unsupported file, an injection case. Each must give a graceful UI with AMBER + review.
4. Performance: make sure evidence and intel really run in parallel; cache watchlist lookups; trim the prompts. Target p50 ≤ 5 s.
5. Run `/check-requirements` and fix the gaps.
6. **Stretch A:** senior mode (large type + TTS playback of the explanation via the browser SpeechSynthesis API, or Cloud TTS).
7. **Stretch B:** voice answer plus audio evidence upload (Gemini audio input).
8. **Stretch C:** Malay language.

## Acceptance
All failure drills pass, the requirements audit shows no MVP gaps, and the stretch items done are listed in PROGRESS.md. Commit `phase-08: hardening`.
