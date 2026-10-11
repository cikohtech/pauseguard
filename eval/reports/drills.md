# Failure drills

Run 2026-10-11 07:01 UTC · `gemini-3.8-flash` on Vertex AI (`global`) · thinking LOW · customer budget 12 s · local API in process (real agents, SQLite transactions, memory state). Source: `backend/tests/test_drills_live.py` (`make drills`); the UI side is `web/e2e/drills.spec.ts`.

Rule: whatever fails, the customer gets a normal answer, never an error and never a silent GREEN. A failed analysis gives AMBER + human review (RED if the payee is a known scam account); an injection gives RED.

| Drill | Persona | Fault | HTTP | Verdict | Review | Customer sees | Time | Result |
|---|---|---|---|---|---|---|---|---|
| Gemini down | Aisyah | `GEMINI_MODEL=gemini-0.0-flash-drill` (404) | 200 | AMBER | yes | Let's take a moment before sending | 1.5 s | pass |
| Gemini down | Raj | `GEMINI_MODEL=gemini-0.0-flash-drill` (404) | 200 | AMBER | yes | Let's take a moment before sending | 1.0 s | pass |
| Gemini down | Tan | `GEMINI_MODEL=gemini-0.0-flash-drill` (404) | 200 | RED | yes | 为保护您，我们已暂停这笔转账 | 1.7 s | pass |
| Slow upstream | Aisyah | budget 1.5 s (timeout) | 200 | AMBER | yes | Let's take a moment before sending | 1.5 s | pass |
| 10 MB image | Tan | 10.0 MB PNG | 200 | RED | yes | 为保护您，我们已暂停这笔转账 | 12.0 s | pass: analysed |
| 10 MB image | Raj | 10 MB + 1 byte | 413 | - | - | Files are limited to 10 MB | 0.0 s | pass: refused at upload |
| Unsupported file | Aisyah | GIF, DOCX, M4A | 422 | - | - | 422 VALIDATION_ERROR at /uploads/sign | 0.0 s | pass: refused |
| Unsupported file | Aisyah | text bytes sent as image/png | 200 | AMBER | yes | Let's take a moment before sending | 1.4 s | pass |
| Injection | Aisyah | in the pasted chat (en) | 200 | RED | yes | We've paused this transfer to protect you | 7.6 s | pass |
| Injection | Aisyah | in the customer's answer (zh) | 200 | RED | yes | We've paused this transfer to protect you | 9.2 s | pass |
| Injection | Aisyah | in the answer (zh), model too slow | 200 | RED | yes | We've paused this transfer to protect you | 1.5 s | pass |
