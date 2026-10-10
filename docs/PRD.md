# PRD: PauseGuard

*"Pause before you pay."* The product name lives in one constant (`PRODUCT_NAME`).

## 1. Problem

- Singapore lost **S$913.1M to scams in 2025 across 41,974 cases**. In **81.8% of cases the victim made the transfer themselves** (Singapore Police Force, Feb 2026: https://www.police.gov.sg/media-hub/police-life/2026/02/scams-and-cybercrime-fell-by-almost-a-quarter-in-2025).
- Top loss types: investment scams, government-official impersonation, job scams, phishing, business email compromise.
- Banks' fraud systems score the *transaction*. In a persuaded payment, the device, password and OTP are all genuine, so the payment looks normal. The proof of the scam is in the conversation (WhatsApp, SMS, call, social media), which the bank never sees.
- Generic "Are you sure?" pop-ups get clicked through. Fraud-team call-backs are slow and have no context.

## 2. Solution

When a customer starts a risky transfer, PauseGuard:
1. Scores the transaction (new payee, amount vs. history, destination type, velocity, time).
2. If risky, opens a short, calm **check-in**: "Who asked you to make this payment?" The customer answers by text or voice and can **upload the screenshot, chat export or call recording** behind the payment.
3. A team of **ADK agents on Gemini** extracts claims, entities and pressure tactics from the evidence, checks them against scam intelligence and Google Search, and classifies the scam typology.
4. A **deterministic policy** combines the signals into a verdict:
   - 🟢 **GREEN / Proceed**: payment continues.
   - 🟡 **AMBER / Pause & explain**: red flags are highlighted *on the customer's own screenshot*, explained in plain language in their language, with a cooling-off option and a "call my trusted contact" button. The customer can still proceed after the cool-off.
   - 🔴 **RED / Hold for review**: the payment is held and a case file is sent to a bank analyst.
5. In the **analyst console**, analysts see a case file with the evidence, red flags, agent reasoning and a recommended action, and decide with one click. Their decisions feed the watchlist.

**Pitch:** *Fraud models check the transaction. PauseGuard checks the conversation that caused it.*

## 3. Personas

| Persona | Who | Need |
|---|---|---|
| **Mrs Tan Mei Ling**, 67, retiree (demo victim) | Uses the banking app for bills; prefers Chinese; trusts authority | To be stopped kindly, without feeling stupid, before losing savings |
| **Raj Kumar**, 29, gig worker (job-scam victim) | Recruited for "task-based" online job; asked to top up | A clear explanation that "paying to earn" is a scam |
| **Nur Aisyah**, 34, teacher (legit user) | Paying a deposit to a new landlord | Not to be blocked or annoyed |
| **Daniel Lim**, fraud analyst at Harbour Bank (fictional) | Reviews held payments | Fast, evidence-backed case files and one-click actions with an audit trail |
| **Head of Fraud** (buyer) | Owns scam losses and regulatory exposure (Singapore's Shared Responsibility Framework) | Fewer losses, few false positives, an explainable audit trail |

## 4. User stories (MVP = must ship)

**Customer**
- C1 (MVP) As a customer, when I start a transfer to a new or unusual payee, I'm asked a short question instead of seeing a generic warning.
- C2 (MVP) I can upload a screenshot (PNG/JPG), a PDF, or paste text of the message that asked me to pay.
- C3 (MVP) I see a clear verdict screen with up to 4 red flags, each pointing to the exact part of my screenshot (bounding box) or quote.
- C4 (MVP) The explanation is in my chosen language (English + Chinese (Simplified) in the MVP; Malay and Tamil are stretch goals).
- C5 (MVP) For AMBER, I can start a 24-hour cooling-off, call my trusted contact, or continue after confirming.
- C6 (MVP) Legit payments get GREEN within one step.
- C7 (stretch) I can answer by voice and upload a call recording (audio).
- C8 (stretch) A large-font "senior mode" toggle.

**Analyst**
- A1 (MVP) A live queue of RED and AMBER cases updates in real time without a page refresh.
- A2 (MVP) A case file shows: transaction risk features, evidence preview with flags overlaid, typology and confidence, watchlist and search matches, agent reasoning summary, and recommended action.
- A3 (MVP) One-click actions: Release, Hold, Escalate, Report as scam, each with an optional note and recorded in the audit log.
- A4 (MVP) "Report as scam" adds the extracted phone numbers, URLs and accounts to the watchlist.
- A5 (MVP) A dashboard shows checks today, verdict split, money protected (sum of RED and AMBER-cancelled amounts), false-positive rate (analyst releases ÷ RED), top typologies, and p50/p95 latency.
- A6 (stretch) An agent trace viewer for each check, linking to Cloud Trace.

**Platform**
- P1 (MVP) One API (`POST /api/v1/checks`) that any bank's payment flow could call.
- P2 (MVP) A benchmark report that compares rules-only and full PauseGuard on the labelled eval set.
- P3 (MVP) Deployed on Cloud Run and Firebase Hosting, with a public demo link and seeded demo accounts.

## 5. Scope

**In scope:** mock banking app (transfer flow only), check-in, evidence analysis (image, PDF, text; audio is stretch), verdicts, analyst console, dashboard, watchlist, synthetic data, eval benchmark, deployment.

**Out of scope:** real bank integration, real authentication of customers, real money movement, card fraud, account takeover detection, model fine-tuning.

## 6. Success metrics (reported in the deck)

| Metric | Target |
|---|---|
| Scam recall on the eval set | ≥ 90%, and higher than rules-only by ≥ 25 points |
| False-positive rate (legit → RED) | ≤ 5% |
| Legit → GREEN or AMBER-pass-through | ≥ 85% |
| Typology accuracy | ≥ 80% |
| Latency, full check (p50 / p95) | ≤ 5 s / ≤ 10 s |
| Cost per check | < US$0.01 (report the actual number) |
| Explanation clarity (human-rated 1–5) | ≥ 4.0 |

These targets are goals. Report real numbers honestly, even when they miss.

## 7. Non-functional requirements

- **Explainable:** every verdict lists its reasons, and the policy rules are written out in `docs/AGENTS_SPEC.md`.
- **Safe defaults:** if a model call fails or times out, the verdict is AMBER plus human review, never GREEN.
- **Accessible:** WCAG 2.1 AA, large tap targets, plain language at a reading age of about 12, no blame language.
- **Private:** PII redacted in logs, evidence auto-deleted after 30 days, data kept in asia-southeast1.
- **Fast:** analysis agents run in parallel; stream progress to the UI ("Checking the message… Checking the payee…").

## 8. Release plan

See `prompts/` (phases 00–11) and `PROGRESS.md`. The MVP must be complete and deployed by the end of phase 10. Phase 11 is the submission package.
