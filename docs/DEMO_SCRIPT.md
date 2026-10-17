# Demo Video Script: 3:00 to 4:00 (target 3:30)

**Official rule:** the video must be 3–4 minutes and must *clearly demonstrate working functionality*. If it's too long it may be penalised. If it doesn't show the product working, the entry doesn't progress. So:
- About **2:20 of the 3:30 is the live, deployed product** being used, with the browser address bar showing **pauseguard-sg.web.app** at least once.
- Don't cut out the analysis wait; shorten it with a quick speed-up only if it's longer than 6 s, and label it "sped up 2×".
- Name **Firebase, Firestore, Cloud Run and Gemini** on screen (scene 8 overlays them on the architecture diagram).
- Aim for 3:30. **Never exceed 3:55 or go under 3:05.** Check the final export length.

Record the **deployed** app at 1080p, with the phone frame on the left and the console on the right (or cut between them). Add captions (`submission/captions.srt`, generated from the voice-over column by `make captions`) and quiet music. The voice-over runs at about 150 words per minute; every line below fits its slot at that pace.

Numbers (all from `eval/reports/benchmark.md`, deployed run `20261016T1447Z_api_test`, and SPF Feb 2026): S$913.1M lost in 2025, 81.8% self-transferred; on 100 held-out cases rules alone stopped 78% of scams, PauseGuard 100% with a 4% false-positive rate, p50 7.6 s, US$0.0070 per check.

| # | Time | Visual | Voice-over |
|---|---|---|---|
| 1 | 0:00–0:12 | Large text: "S$913 million lost to scams in Singapore in 2025." Then "81.8% of victims sent the money themselves." Source small: Singapore Police Force, Feb 2026. | Last year, scammers took 913 million dollars from people in Singapore. In four out of five cases, the victim pressed send themselves. |
| 2 | 0:12–0:25 | Title card: a bank's fraud check, device ✓, password ✓, OTP ✓ → "Looks normal". | To the bank, those payments look normal: the right phone, the right password, the right one-time code. The evidence is in the conversation that persuaded them, and banks never see it. |
| 3 | 0:25–0:35 | Browser shows the **live URL** pauseguard-sg.web.app → landing page, logo **PauseGuard**, "Pause before you pay." | PauseGuard checks the conversation, not just the transaction. This is the live prototype, running on Google Cloud. |
| 4 | 0:35–1:30 | **Mrs Tan**: the fake "MAS officer" WhatsApp chat → Harbour Bank app → new payee, S$8,000 → Send → check-in sheet → "A government officer" + her screenshot → step ticks (real time, ~10 s) → **RED** screen: numbered boxes on her (Chinese) screenshot, plain-English explanation, "Call my son" and 1799. | Mrs Tan is 67. A man claiming to be from MAS tells her to move her savings to a safe account. When she sends eight thousand dollars to a new account, PauseGuard asks her one simple question: who asked you to make this payment? She shares the chat. Gemini agents read her screenshot, while the payee and the scammer's number are checked against the bank's watchlist. In about ten seconds, the payment is held. She sees exactly why, on her own screenshot, in plain words, with a button to call her son and the anti-scam helpline. |
| 5 | 1:30–2:00 | **Console** (second window, live): the case is already in the queue. Summary → Evidence tab with the boxes → Transaction risk tab with the spike on the 90-day chart → Intel tab → press **S** (Report as scam) → toast "3 entities added to the watchlist". | At the bank, the case reached the analyst console before Mrs Tan's screen even changed, through Firestore's realtime listener. Gemini has written the case file: the evidence with the red flags boxed, her 90-day history with this transfer standing out, and web intel grounded in Google Search. One key reports the scam, and the scammer's number, account and link are blocked for every customer. |
| 6 | 2:00–2:22 | **Raj (job scam)**: S$450 "top-up" → "A job recruiter" + the pasted Telegram text → **AMBER**: "Paying to earn is a known job scam" → taps "Pause for 24 hours". | Not every case needs a hard stop. Raj is told to top up four hundred and fifty dollars to unlock his commission. PauseGuard explains the pay-to-earn job scam and suggests a 24-hour pause. Raj stays in control. |
| 7 | 2:22–2:40 | **Aisyah (legit)**: S$3,200 deposit to a new landlord, attaches the tenancy PDF → **GREEN** "Looks good" → sent. | And it stays out of the way. Aisyah is paying a deposit to her new landlord and attaches the tenancy agreement. Gemini reads the PDF, finds nothing suspicious, and the payment goes through. |
| 8 | 2:40–3:02 | `docs/img/architecture.png` with four labels popping in: **Firebase Hosting & Auth · Cloud Run · Gemini on Vertex AI (5 ADK agents) · Firestore** (+ BigQuery) → 3 s of the Cloud Trace agent trace (`docs/img/agent-trace.jpg`). | Under the hood: the app is on Firebase Hosting with Firebase Auth. Five ADK agents run on Cloud Run, with Gemini on Vertex AI. Firestore stores the cases and powers the live console, and BigQuery scores transaction risk. The verdict itself comes from plain, tested rules, so it's auditable. |
| 9 | 3:02–3:17 | The benchmark chart (`eval/reports/charts/benchmark_recall_fpr.png`) with the three headline numbers as text: 78% → 100% recall, 4% false positives, < 1 cent per check. | On a hundred held-out test cases, rules alone stopped 78 percent of scams. PauseGuard stopped all of them, with a 4 percent false-positive rate, for under a cent per check. |
| 10 | 3:17–3:30 | Landing page with the URL, then "Team Cikoh: Md Asif · Ananya Verma" and the GitHub link. | Fraud models check the transaction. PauseGuard checks the conversation. Try it live at pauseguard-sg dot web dot app. |

## Recording checklist (scene by scene)

**Before you record (≈ 15 min)**
- [ ] `make deploy-api MIN_INSTANCES=1` (≈ US$2/day; no cold start mid-take), then `make smoke`. Record only after a smoke run where all three scenarios give the expected verdict; if Gemini is slow that hour (a check falls back to AMBER + review), wait and retry.
- [ ] Reset the demo data: `make smoke` ends with `reset-demo`; otherwise `curl -X POST -H "X-Admin-Token: $(gcloud secrets versions access latest --secret admin-reset-token)" <API>/api/v1/admin/reset-demo`.
- [ ] Chrome, a clean profile (no extensions, bookmarks bar hidden), zoom 100%, window 1920×1080. Two windows side by side: left `https://pauseguard-sg.web.app/app` (the phone frame), right `https://pauseguard-sg.web.app/console` (sign in with the prefilled demo login).
- [ ] Do one full dry run of scenes 4–7, then `reset-demo` again so the console queue starts empty.
- [ ] Screen recorder at 1080p 30 fps (QuickTime or OBS); system notifications off (Do Not Disturb).

**Scenes**
- [ ] **1–2 (title cards, 25 s):** make two simple cards in Slides/Keynote (white, the PauseGuard teal, big numbers). Source line on card 1.
- [ ] **3 (10 s):** the landing page, address bar visible with `pauseguard-sg.web.app`.
- [ ] **4 (55 s, Mrs Tan):** start on her fake WhatsApp chat (`data/demo/tan_mas_chat.png` full screen for 3 s), then the app: persona picker → Mrs Tan → Transfer → **Prefill demo scenario** → Review transfer → Send → in the check-in tap **Use the demo answer** (attaches the screenshot) → **Check now**. Keep the real wait (speed up 2× only if it is over 6 s, and label it). Hold on the RED screen; scroll to the boxed screenshot.
- [ ] **5 (30 s, console):** the right window already shows the new RED case. Open it → Summary (wait for the case file) → Evidence → Transaction risk → Intel → press **S** → the toast.
- [ ] **6 (22 s, Raj):** persona picker → Raj → Transfer → Prefill demo scenario → Review → Send → **Use the demo answer** → Check now → AMBER → **Pause for 24 hours**.
- [ ] **7 (18 s, Aisyah):** Aisyah → Transfer → Prefill → Review → Send → Use the demo answer (the PDF) → Check now → GREEN → sent.
- [ ] **8 (22 s):** `docs/img/architecture.png` full screen with the four product names as overlays; then `docs/img/agent-trace.jpg` for 3 s.
- [ ] **9 (15 s):** `eval/reports/charts/benchmark_recall_fpr.png` with the numbers as text.
- [ ] **10 (13 s):** landing page + team card.

**After recording**
- [ ] Edit the scenes together; keep real waits. Export 1080p MP4 and **check the length is between 3:05 and 3:55**.
- [ ] Voice-over: read the right-hand column (also in `submission/voiceover.txt`). Captions: upload `submission/captions.srt`, or paste `voiceover.txt` into YouTube Studio → Subtitles → "Auto-sync" so the timings follow your actual recording.
- [ ] Upload to YouTube as **Unlisted or Public** (never Private). Title: "PauseGuard: stopping scams at the moment of payment (Google Cloud AI Builder Cup 2026)".
- [ ] Open the link in an incognito window to check it plays.
- [ ] `make deck VIDEO_URL=https://youtu.be/...` to put the link in the deck, and put it in `submission/SUBMIT_CHECKLIST.md`.
- [ ] Optional: keep a backup MP4 in Google Drive (anyone with the link can view).
- [ ] Afterwards: `make deploy-api` (back to min 0) unless a judging day is known.

## Live finale pitch (Singapore, 4 Dec, if shortlisted)

Use the same story arc, live on stage. Bring a phone that already has the app open, plus an offline backup video. Prepare answers to the judge questions in `private/judge-questions.md` (git-ignored).
