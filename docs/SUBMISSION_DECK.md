# Submission Deck Content (maps 1:1 to the official template)

`make deck` fills the official template (`reference/Submission_Template_AI_Builder_Cup.pptx`) with this content and writes `submission/PauseGuard_Submission.pptx` (`scripts/build_deck.py`). The script reads the bullets (`- `, nested `  - `) and tables under each numbered heading below, so **edit the text here, not in the script**; the layout and images are in the script. Lines starting with `>` are notes for us and never reach the slides. `**bold**` is kept.

> Numbers: the deployed benchmark run `20261016T1447Z_api_test` (`eval/reports/benchmark.md`, "For the deck" table) and `docs/COSTS.md`. Problem stats: Singapore Police Force, Feb 2026. Re-run `make deck` after changing anything.

## 1. Team details
- Team name: Cikoh
- Team leader name: Md Asif
- Problem Statement: Authorised-push-payment scams. In 81.8% of Singapore's 41,974 scam cases in 2025 the victim sent the money themselves (S$913.1M lost; SPF, Feb 2026). The device, password and OTP are genuine, so bank fraud models see a normal payment; the evidence is in the chat that persuaded the customer, which the bank never sees.

## 3. Brief about the idea
- **PauseGuard is an AI copilot inside the bank's payment flow.** Fraud models check the transaction; PauseGuard checks the conversation.
- When a transfer looks risky, the app asks one question, "Who asked you to make this payment?", and the customer can share the chat, screenshot or PDF behind it.
- **Gemini agents built with ADK** read the evidence (multimodal), find red flags and the scammer's number, account and links, and check them against a shared watchlist and the live web.
- **A transparent rule policy, not the LLM, decides:** GREEN (send), AMBER (pause and explain, the customer decides) or RED (hold for a bank analyst).
- The customer sees exactly why: numbered boxes on their own screenshot, in English or Chinese. The analyst gets a live case file and can block the scammer for every customer in one click.

## 4. Opportunities
- How different is it from any of the other existing ideas?
  - Transaction monitoring and generic "beware of scams" pop-ups never see the social engineering. PauseGuard analyses the actual conversation at the moment of payment, multimodally, and explains the specific red flags to this customer.
- How will it be able to solve the problem?
  - It catches persuaded payments that look normal to fraud models (rules alone missed 22% of our test scams), breaks the scammer's spell with a personal explanation, keeps legitimate payments flowing (4% false positives vs 44% for rules), and turns each held payment into a ready case file and watchlist entry for the bank.
- USP of the proposed solution
  - "Check the conversation, not just the transaction": explainable (boxes on the screenshot, written rules), bilingual, human-in-the-loop, safe by default (a failure never says GREEN), and one API call for a bank to add to its payment flow.

## 5. List of features offered by the solution
- **For the customer (bank app)**
  - Smart trigger: transaction risk from BigQuery features; every first payment to a new payee gets a check-in
  - One-question check-in: quick replies, free text, screenshot or PDF upload, pasted chat
  - Live progress ticks while the agents work (server-sent events)
  - Red flags boxed on the customer's own screenshot and marked in pasted text
  - Explanations in English or Chinese; no blame, plain language
  - AMBER: pause 24 h, call a trusted contact, or continue after confirming; RED: payment held, 1799 anti-scam helpline
  - WCAG 2.1 AA, keyboard and screen-reader tested, on phone and desktop
- **For the bank (analyst console)**
  - Realtime queue (Firestore listener): a held payment appears before the customer's screen does
  - Case view: AI case file, evidence with boxes, risk chart, watchlist and web intel with sources, audit trail
  - One-key decisions (release, hold, escalate, report scam) with notes and a full audit log
  - Self-learning watchlist: a reported scam blocks its number, account and links for everyone
  - Dashboard: money protected, verdict mix, false-positive rate, latency, cost per check, top scam types
  - Safety: prompt-injection hard stop, PII redaction, 30-day evidence deletion, Singapore data region

## 6. Process flow diagram or Use-case diagram
> Image: `docs/img/process-flow.png` (from `docs/diagrams/process-flow.mmd`, `make diagrams`).

## 7. Wireframes/Mock diagrams of the proposed solution (optional)
> Images: the live app's phone screens from `docs/img/screens/` (`make screens`), with these captions.
- Persona picker: three synthetic customers
- One-question check-in, evidence attached
- AMBER: the job-scam pattern explained
- RED: payment held, red flags boxed
- The same RED for Mrs Tan, in Chinese

## 8. Architecture diagram of the proposed solution
> Image: `docs/img/architecture.png` (from `docs/diagrams/architecture.mmd`), plus four captions.
- **Firebase:** Hosting serves the customer app and analyst console; Auth signs in customers (anonymous) and analysts (role claim)
- **Firestore:** checks, cases, watchlist, audit; realtime listeners drive the live console
- **Cloud Run:** FastAPI + ADK agents in Singapore; parallel analysis with a 12 s budget
- **Gemini on Vertex AI:** 5 ADK agents: evidence (vision + boxes), explainer, case file, scam intel, Google Search

## 9. Technologies to be used in the solution
- **Google Cloud AI**
  - Gemini 3.8 Flash on Vertex AI: multimodal (images, PDFs), bounding boxes, structured JSON output
  - Agent Development Kit (ADK): 5 LlmAgents, function tools, AgentTool, eval sets, OpenTelemetry tracing
  - Grounding with Google Search for live scam intelligence
- **Google Cloud platform**
  - Cloud Run (asia-southeast1) · Firebase Hosting · Firebase Auth · Firestore (realtime) · BigQuery · Cloud Storage (signed URLs, 30-day lifecycle) · Secret Manager · Cloud Logging · Cloud Trace · Cloud Scheduler · Cloud Monitoring · Cloud Build · Artifact Registry
- **Application stack**
  - Python 3.12, FastAPI, Pydantic v2, pytest · React, TypeScript, Vite, Tailwind CSS, shadcn/ui, Recharts · Playwright + axe for accessibility tests · SQLite + Firebase emulators for local development

## 10. Estimated implementation cost (optional)
- **Prototype (live through judging): ≈ US$8–14 a month.** Scales to zero; Gemini ≈ US$6 for ~900 checks; BigQuery, Firestore, Storage and Hosting stay in the free tiers.
- **Pilot, one bank, 50,000 checks a month: ≈ US$2,300 a month, ≈ US$0.046 per check.**
  - Gemini tokens US$351 (5,216 in / 831 out per check, measured; US$0.0070 a check)
  - Google Search grounding US$1,874 (2.8 queries a check, only on AMBER/RED); Cloud Run (1–2 warm instances) US$58–121; BigQuery US$12; Firestore, Storage, Scheduler ≈ US$2
- **Next optimisation:** cache web intel per domain and skip it on watchlist hits → ≈ US$1,050 a month (≈ US$0.021 a check).
- **Return:** the median scam loss in Singapore is S$1,644 (SPF 2025). One stopped scam pays for ≈ 27,500 checks; the pilot breaks even at about two stopped scams a month.
- Prices: Google Cloud list prices, Singapore region where applicable, retrieved Oct 2026 (Gemini 3.8 Flash introductory price until 31 Dec 2026). Method and sources: docs/COSTS.md.

## 11. Snapshots of the prototype
> Images: desktop screenshots of the live app from `docs/img/screens/`, with these captions.
- Analyst console (live, Firestore listener): Mrs Tan's case, her screenshot with the red flags boxed, the entities on the watchlist and what the evidence says
- Dashboard: money protected, verdicts, false-positive rate, latency and cost per check
- Landing page: both entry points and the problem statistic

## 12. Prototype Performance report/Benchmarking
- 100 held-out synthetic cases (50 scams in 8 typologies, 50 legitimate look-alikes; English and Chinese; images, PDFs, text), frozen before any system ran. Run through the deployed API on Cloud Run, gemini-3.8-flash, 16 Oct 2026.

| System | Scam recall | False positives | Legit → RED | Typology | p50 latency | Cost / check |
|---|---|---|---|---|---|---|
| Rules only | 78% | 44% | 0% | n/a | 0.9 s | $0 |
| Gemini, single prompt | 100% | 4% | 0% | 96% | 5.4 s | $0.0012 |
| **PauseGuard** | **100%** | **4%** | **0%** | **92%** | **7.6 s** | **$0.0070** |

- Rules alone miss 1 in 5 scams and stop 44% of good payments; reading the conversation fixes both.
- A single prompt is as accurate here but has no time budget: 12/100 answers took over 12 s. PauseGuard adds an auditable verdict, a safe 12 s fallback, boxes, explanations, case files and an injection hard stop.
- Both PauseGuard false alarms were timeouts (AMBER + review): 48/48 scams and 0/48 legit on finished analyses. Same results across languages and age groups.
- Limits: synthetic data and our own labels; p50 7.6 s misses our 5 s target. Full report, fairness tables and charts: eval/reports/benchmark.md.

## 13. Additional Details/Future Development (if any)
- **Bank pilot** with consented data: measure real recall, false positives and the share of checks that need an analyst
- **More signals:** telco scam-call flags and national anti-scam feeds into the shared watchlist
- **More people:** voice-note and call check-ins; Malay, Tamil, Bahasa Indonesia, Thai and Vietnamese; a senior mode
- **Trusted-contact co-approval** for older customers' large first payments
- **Platform:** Vertex AI Agent Engine with session memory; cheaper web intel (caching, skipping on watchlist hits); a weekly eval re-run for drift
- **Policy fit:** aligned with Singapore's Shared Responsibility Framework and MAS guidance; then a path across JAPAC banks and wallets

## 14. Links
- GitHub Public Repository: https://github.com/cikohtech/pauseguard
- Demo Video Link (3 Minutes): VIDEO_URL
- Final Product Link: https://pauseguard-sg.web.app (customer app: /app · analyst console: /console, demo login prefilled: analyst@harbourbank.example / HarbourDemo2026)

> `VIDEO_URL` is replaced by `make deck VIDEO_URL=https://youtu.be/...` once the video is on YouTube.

## 15. How we use Firebase, Firestore, Cloud Run and Gemini
> The template's spare slide (15) carries this, since the brief description must explain all four.
- **Firebase:** Hosting serves the React app (customer banking mock, analyst console, landing page); Auth gives customers anonymous sign-in and analysts email/password with a role=analyst custom claim that the API and Firestore rules check.
- **Firestore:** stores checks, cases, the scam watchlist, the audit log and analytics; its realtime listener drops a held payment into the analyst console in under a second, and an analyst's "report scam" updates the watchlist for every customer.
- **Cloud Run:** hosts the FastAPI + ADK agent backend in Singapore: it runs the evidence agent and watchlist lookups in parallel, applies the deterministic policy, streams progress to the app and finishes the case file in the background.
- **Gemini (3.8 Flash on Vertex AI):** powers all 5 ADK agents: it reads screenshots and PDFs and boxes the red flags, writes the English/Chinese explanation and the analyst case file, and checks unknown sites with Google Search grounding, all as validated structured JSON.

## Likely judge questions
Kept in the git-ignored `private/judge-questions.md` (pitch prep, not for the public repo).
