# Demo Video Script: 3:00 to 4:00 (target 3:30)

**Official rule:** the video must be 3–4 minutes and must *clearly demonstrate working functionality*. If it's too long it may be penalised. If it doesn't show the product working, the entry doesn't progress. So:
- At least **2:30 of the video is the live, deployed product** being used, with the browser address bar showing the real URL at least once.
- Don't cut out the analysis wait; shorten it with a quick speed-up only if it's longer than 6 s, and label it "sped up 2×".
- Name **Firebase, Firestore, Cloud Run and Gemini** on screen.
- Aim for 3:30. **Never exceed 3:55 or go under 3:05.** Check the final export length.

Record the **deployed** app at 1080p, with the phone frame on the left and the console on the right (or cut between them). Add captions and quiet music. Voice-over is about 150 words per minute.

| Time | Visual | Voice-over |
|---|---|---|
| 0:00–0:15 | Large text: "S$913 million lost to scams in Singapore in 2025." Then "In 82% of cases, victims sent the money themselves." Source shown small. | "Last year, scammers took 913 million dollars from people in Singapore. In four out of five cases, the victim pressed send themselves." |
| 0:15–0:30 | Bank fraud check: device ✓, password ✓, OTP ✓ → "Looks normal" | "To a bank's fraud system, those payments look normal. The evidence is in the conversation that persuaded them, and banks never see it." |
| 0:30–0:40 | Browser shows the **live URL** → landing page, logo **PauseGuard**, "Pause before you pay." | "PauseGuard checks the conversation, not just the transaction. This is the live prototype running on Google Cloud." |
| 0:40–1:40 | **Mrs Tan (Chinese UI)**: the fake "MAS officer" chat on her phone → Harbour Bank app → new payee, S$8,000 → Send → check-in sheet → "A government officer" + upload screenshot → step ticks (real time) → **RED** screen: 4 numbered boxes on her screenshot, Chinese explanation, "Call my son" and 1799. | "Mrs Tan is 67. A man claiming to be from MAS tells her to move her savings to a 'safe account'. When she sends the transfer, PauseGuard sees a large first payment to a new account and asks one simple question. She shares the chat. Gemini agents read the screenshot, find the scammer's number on our watchlist and recognise a government-impersonation scam. PauseGuard holds the payment and shows her exactly why, in her own language, on her own screenshot." |
| 1:40–2:10 | **Console** (the second window, live): the case slides in. Summary → Evidence tab with overlays → Risk tab with the spike on the 90-day chart → Intel tab with the watchlist hit → press **S** (Report as scam) → toast "3 entities added to watchlist". | "At the bank, the analyst already has the full case file through Firestore in real time: evidence, risk factors, intel and a recommended action. One click reports the scam, and the scammer's number, account and link are blocked for every customer." |
| 2:10–2:35 | **Raj (job scam, English)**: S$450 "top-up" → answers "A job recruiter" and pastes the Telegram text → **AMBER**: "Paying to earn is a known job scam" → taps "Pause for 24 hours". | "Not every case needs a hard stop. Raj is asked to 'top up' to unlock his commission. PauseGuard explains the job-scam pattern and suggests a 24-hour pause, and Raj stays in control." |
| 2:35–2:55 | **Aisyah (legit)**: S$3,200 deposit to a new landlord, uploads the tenancy PDF → **GREEN** "Looks good". | "And it stays out of the way. Aisyah paying her new landlord goes through in one step." |
| 2:55–3:25 | Architecture diagram with labels for **Firebase Hosting & Auth · Cloud Run · Gemini on Vertex AI (ADK agents) · Firestore · BigQuery** → 3 s of a Cloud Trace agent trace → the benchmark chart. | "Under the hood: the app is on Firebase. Five ADK agents run on Cloud Run with Gemini for multimodal analysis and explanations. Firestore powers cases and the live console, and BigQuery scores transaction risk. On our 100-case test set, rules alone stopped X% of scams. PauseGuard stopped Y%, with a Z% false-positive rate, in about N seconds, for under a cent per check." *(Use the real numbers from `eval/reports/benchmark.md`.)* |
| 3:25–3:35 | Landing page with the URL, then the team names. | "PauseGuard plugs into any bank's payment flow with a single API. Fraud models check the transaction; PauseGuard checks the conversation. Try it live at [URL]." |

**Recording checklist**
- Run `/admin/reset-demo` first, and set min-instances=1 (no cold start).
- Record each scene separately and edit them together, keeping real wait times.
- Export, check the length is 3:05–3:55, and add burned-in captions or an SRT.
- Upload to YouTube as **Public or Unlisted** (never Private), then open the link in incognito to check it.
- Keep a backup MP4 in Google Drive (public link) in case the form allows an alternative.

## Live finale pitch (Singapore, 4 Dec, if shortlisted)

Use the same story arc, live on stage. Bring a phone that already has the app open, plus an offline backup video. Prepare answers to the judge questions in `private/judge-questions.md` (git-ignored).
