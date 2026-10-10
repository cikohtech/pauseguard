# Hackathon Requirements: Google Cloud AI Builder Cup 2026

This is the **non-negotiable checklist**. Run `/check-requirements` (or ask Claude Code to audit against this file) at the end of every phase from phase 08 onward.

## 0. What we know about the contest

Sources: the submission template deck from the organisers, the organisers' briefing session (themes and recommended stack, as shared by the team), and public event listings (e.g. https://opportunitiescorners.com/google-cloud-ai-builder-cup-2026-in-singapore/).

- Organised by **Hack2skill** with **Google Cloud**. JAPAC region. Teams of up to 4.
- Build a **functional prototype on Google Cloud** for one of six themes. **Ours: BFSI** (fraud detection, risk mitigation, hyper-personalised customer experience).
- **Grand finale in person in Singapore, 4 Dec 2026**, pitching to Google Cloud and industry judges.
- **Prizes (USD 30k):** Winner $10k · 1st runner-up $7k · 2nd runner-up $5k · **Best Use of Google Cloud AI Tools** $2k · **Most Impactful Solution** $2k · **Social Choice** $2k · **Best UI/UX** $2k.
- **Recommended stack:** Gemini (they suggested 1.5 Flash; it's retired, so use the current Flash), **Agent Development Kit (ADK)**, deploy on **Cloud Run or Firebase**, databases **Firestore** (default) / Cloud SQL / **BigQuery**, SQLite for local dev. PauseGuard uses all the recommended pieces.

> ⏰ **PROTOTYPE SUBMISSION CLOSES ≈ 18 Oct 2026, 18:28 UTC (≈ 19 Oct, 02:28 Singapore time).** This was worked out from the dashboard countdown on 10 Oct; **confirm the exact time on the Hack2skill dashboard.** Our plan is to **submit by the end of 17 Oct** and keep 18 Oct as a buffer. Follow the 8-day plan in `PROGRESS.md`.

## 0.1 The five mandatory submission rules (official, summarised in §4)

1. **Pitch deck on the prescribed template.** Any other format may be disqualified.
2. **Video demo, 3 to 4 minutes,** that clearly shows the solution *working*. Over-length videos may be penalised or dropped. If the video doesn't show working functionality, the entry doesn't progress to prototype evaluation.
3. **Deployed prototype link** that is valid, accessible and **working for the whole evaluation period**. If anything (app, APIs, integrations) is down during evaluation, there are no retries or allowances.
4. **GitHub repository** that stays accessible for the whole evaluation period, with the source code and supporting materials.
5. **Brief description** of what we built, which **must explain how we use Firebase, Firestore, Cloud Run and Gemini.** All four are mandatory in our build (see §2) and are covered in `docs/BRIEF_DESCRIPTION.md`.

All submission links must work and be publicly accessible.

## 1. Required submission deliverables (from the official template)

| # | Template slide / item | Where it comes from in this repo | Done |
|---|---|---|---|
| 1 | Team details: team name, team leader name, **problem statement** | `docs/SUBMISSION_DECK.md` §1 | ☐ |
| 2 | Brief about the idea | `SUBMISSION_DECK.md` §2 | ☐ |
| 3 | Opportunities: how it's different, how it solves the problem, USP | `SUBMISSION_DECK.md` §3 | ☐ |
| 4 | List of features | `SUBMISSION_DECK.md` §4 (must match what's actually built) | ☐ |
| 5 | Process flow / use-case diagram | `docs/img/process-flow.png` (generated from Mermaid in phase 11) | ☐ |
| 6 | Wireframes / mock diagrams (optional, but do it for the UI/UX prize) | `docs/img/screens/*.png` | ☐ |
| 7 | Architecture diagram | `docs/img/architecture.png` | ☐ |
| 8 | Technologies used | `SUBMISSION_DECK.md` §8 | ☐ |
| 9 | Estimated implementation cost (optional, but do it) | `SUBMISSION_DECK.md` §9 + `docs/COSTS.md` | ☐ |
| 10 | Snapshots of the prototype | `docs/img/screens/*.png` (real app, deployed) | ☐ |
| 11 | **Prototype performance report / benchmarking** | `eval/reports/benchmark.md` + charts | ☐ |
| 12 | Additional details / future development | `SUBMISSION_DECK.md` §12 | ☐ |
| 13 | **Public GitHub repository** link | repo is public, README complete, no secrets | ☐ |
| 14 | **Demo video, 3–4 minutes (target 3:30)**, showing the live product working | `docs/DEMO_SCRIPT.md` → upload to YouTube (Public or Unlisted, never Private) | ☐ |
| 15 | **Final product link** (live), working throughout evaluation | Firebase Hosting URL, with demo logins working; see `DEPLOYMENT.md` §7 (uptime) | ☐ |
| 16 | **Brief description** naming how we use **Firebase, Firestore, Cloud Run and Gemini** | `docs/BRIEF_DESCRIPTION.md` | ☐ |

The template says to download it (File › Download › .pptx), edit the copy and submit the final version. Don't request edit access. A copy is in `reference/Submission_Template_AI_Builder_Cup.pptx`.

## 2. Technical requirements

**Mandatory (named in the official submission rules; the brief description must explain each):**
- ☐ **Firebase**: Hosting for the web app + Firebase Auth (anonymous auth for customers, email/password for analysts)
- ☐ **Firestore**: checks, cases, watchlist, audit log; realtime listeners drive the live analyst console
- ☐ **Cloud Run**: the FastAPI + ADK agent backend
- ☐ **Gemini**: every LLM call (evidence analysis, intel, explanations, case files)

**Our own bar for "Best Use of Google Cloud AI":**

- ☐ Gemini on **Vertex AI** (not just an AI Studio key) for all LLM calls
- ☐ **ADK** multi-agent design with at least 4 distinct agents and tools, visible in the code and the architecture diagram
- ☐ **Multimodal**: images and PDFs in the MVP; audio as stretch
- ☐ **Google Search grounding** used for the intel checks
- ☐ **Structured output** with Pydantic schemas, plus **bounding boxes** from Gemini vision
- ☐ **Cloud Run** serving the API and agents; **Firebase Hosting** for the web app
- ☐ **BigQuery** for transaction features and the analytics dashboard
- ☐ **Firestore** realtime for the analyst console
- ☐ **Cloud Storage** with a lifecycle policy; **Secret Manager**; **Cloud Logging / Trace**
- ☐ SQLite local-dev path working (`DATA_BACKEND=sqlite`), as the organisers suggested
- ☐ The README has a "Google Cloud services used, and why" table

## 3. What each prize needs from us

| Prize | What judges must see | Our evidence |
|---|---|---|
| Overall winner / runners-up | Real problem, working product, strong demo, feasibility, business value | S$913M problem stat, live app, benchmark vs. baseline, pilot path for banks |
| Best Use of Google Cloud AI | Deep, idiomatic use of Gemini, ADK and GCP | §2 checklist, architecture slide, agent trace screenshot |
| Most Impactful | Measurable harm prevented, for vulnerable people | Recall/FPR numbers, "money protected" metric, elderly persona, multilingual |
| Social Choice | A story people share | Mrs Tan's story in the video, emotional but honest; post a short clip on LinkedIn/X with the event hashtag (check the official rules for the voting method) |
| Best UI/UX | Polished, accessible, delightful | `UI_SPEC.md`: evidence overlay, step-tick progress, senior mode, bilingual, WCAG AA |

## 4. Official rules (verbatim, as pasted by Asif on 10 Oct 2026 from the Hack2skill "Prototype Submission" module)

```
Prototype Submission
MODULE CLOSING IN 08d09h07m   (as seen at 2026-10-10 09:21 UTC)

Mandatory Submission Rules:
* Pitch Deck: Participants must submit their pitch deck using the prescribed template provided for the
  challenge. Submissions that do not follow the required format may be subject to disqualification
* Video Demonstration: Participants must submit a 3 to 4 minute video demonstration of their solution. The
  video must clearly demonstrate the working functionality of the submitted solution. Videos exceeding the
  prescribed duration may attract a penalty or may result in the submission not progressing further in the
  evaluation process. If the video does not adequately demonstrate the working functionality of the solution,
  the submission will not progress to the prototype evaluation step, in accordance with the defined ladder process.
* Deployed Prototype Link: Participants must provide a valid and accessible link to a deployed, working
  prototype. The prototype must remain functional throughout the evaluation process. If the application, APIs,
  integrations, or any other deployment-related components are unavailable or non-functional during evaluation,
  no additional consideration, retries, or allowances will be provided. The submission will be evaluated based
  on its functionality at the time of evaluation.
* GitHub Repository: Participants must provide an accessible GitHub repository containing the relevant source
  code and supporting materials. The repository must remain accessible throughout the evaluation process.
* Brief description: Brief description of what you have built (please include how you are leveraging Firebase,
  Firestore, Cloud Run and Gemini in your submission).

Instructions: Make sure all the submission links are working and publicly accessible and inculcates all the
tech mentioned in the submission rules
```

Judging criteria and their weights weren't included. If they appear on the dashboard, paste them here too.

## 5. Final pre-submission audit (phase 11)

- ☐ Live URL opens in an incognito window on mobile and desktop; the persona picker works; the analyst demo login works
- ☐ All 3 demo scenarios work end to end on the deployed stack, 3 times in a row
- ☐ `/admin/reset-demo` works
- ☐ The repo is public, the licence is set (MIT or Apache-2.0), README complete, `.env.example` present, **no secrets in git history** (run `gitleaks` or `trufflehog`)
- ☐ The benchmark report contains real numbers from the deployed model, with the date and model ID
- ☐ The video is **between 3:00 and 4:00** (target 3:30), has captions, shows the **live deployed URL** in the browser bar, and shows every core flow actually working (no mockups, no slides-only sections longer than 30 s)
- ☐ The video names Firebase, Firestore, Cloud Run and Gemini on screen
- ☐ YouTube visibility is Public or Unlisted, and the link opens in an incognito window
- ☐ The brief description (`docs/BRIEF_DESCRIPTION.md`) explains Firebase, Firestore, Cloud Run and Gemini usage
- ☐ The uptime safeguards in `DEPLOYMENT.md` §7 are all in place (min-instances 1, uptime check + alert, daily demo reset, no billing cap, frozen release)
- ☐ The GitHub repo is public and opens in an incognito window
- ☐ The deck is filled in on the official template, every slide is answered, and the links work
- ☐ GCP budget alert set; min-instances=1 only on demo/judging days
- ☐ Every number in the deck matches the benchmark report
