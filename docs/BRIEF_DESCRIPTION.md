# Brief Description (paste into the submission form)

The rules require us to explain how we use **Firebase, Firestore, Cloud Run and Gemini**. Update the numbers in [brackets] after the benchmark, and keep the description under the form's character limit, if it has one. A ~250-word version and a ~100-word version follow.

## Standard version (~250 words)

**PauseGuard** stops scams at the moment a bank customer is about to send money. In Singapore, 82% of scam cases are victims transferring money themselves (S$913M lost in 2025). The payment looks normal to the bank because the evidence of the scam sits in the WhatsApp chat or phone call that persuaded them. When a transfer looks risky, PauseGuard asks one quick question and lets the customer share that chat or screenshot. AI agents then explain the red flags on the customer's own screenshot, in their language, and either let the payment go, pause it, or hold it for a bank analyst.

**How we use Google Cloud:**
- **Gemini** (Flash, on Vertex AI) powers five agents built with the Agent Development Kit. It reads screenshots and PDFs multimodally, marks red flags with bounding boxes, checks unknown websites with Google Search grounding, and writes bilingual (English/Chinese) customer explanations and analyst case files as structured JSON.
- **Cloud Run** hosts the FastAPI + ADK agent backend in Singapore (asia-southeast1). It runs the agents in parallel and returns a verdict in about [N] seconds.
- **Firestore** stores checks, cases, the scam watchlist and the audit log. Its realtime listeners make held payments appear instantly in the analyst console.
- **Firebase** Hosting serves the customer banking app and the analyst console. Firebase Auth handles customer and analyst sign-in.
- **BigQuery** computes transaction-risk features and dashboard analytics.

On our [100]-case test set, rules alone stopped [X]% of scams; PauseGuard stopped [Y]% with a [Z]% false-positive rate, at about $[C] per check.

## Short version (~100 words)

PauseGuard stops authorised-push-payment scams at the moment of transfer by analysing the conversation that persuaded the customer, not just the transaction. **Gemini** (via ADK multi-agent, multimodal) reads the customer's chat screenshot, flags scam tactics on the image and explains them in their language. **Cloud Run** serves the agent backend. **Firestore** stores cases and the watchlist and powers the realtime analyst console. **Firebase** hosts the customer app and console and handles auth. BigQuery scores transaction risk. On our test set, it stopped [Y]% of scams vs. [X]% for rules alone.
