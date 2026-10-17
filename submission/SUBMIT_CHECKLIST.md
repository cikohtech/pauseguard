# Submit checklist: Google Cloud AI Builder Cup 2026 (team Cikoh)

**Deadline:** prototype submission closes ≈ **18 Oct 2026, 18:28 UTC (19 Oct, 02:28 SGT)**; confirm on the Hack2skill dashboard. Our target: submitted by the end of **17 Oct**.

Open every link in an **incognito window** (and once on a phone on mobile data) before you paste it into the form, and tick the box.

| # | What the form asks for | Link / file | Opened in incognito |
|---|---|---|---|
| 1 | Pitch deck on the official template | `submission/PauseGuard_Submission.pptx` (built by `make deck VIDEO_URL=…` from the official template; 16 slides) | ☐ |
| 2 | Demo video, 3–4 min, YouTube **Public or Unlisted** | `https://youtu.be/…` (record with `docs/DEMO_SCRIPT.md`; captions `submission/captions.srt`) | ☐ |
| 3 | Deployed prototype | **https://pauseguard-sg.web.app** (customer app `/app`, analyst console `/console`, demo login prefilled: `analyst@harbourbank.example` / `HarbourDemo2026`) | ☐ |
| 4 | GitHub repository (public) | **https://github.com/cikohtech/pauseguard** | ☐ |
| 5 | Brief description (Firebase, Firestore, Cloud Run, Gemini) | paste `submission/brief_description.txt` (275 words, 1,669 characters); if the form has a tight limit, use the short version in `docs/BRIEF_DESCRIPTION.md` (99 words) | n/a |

## Before you press Submit

- [ ] The video is between **3:05 and 3:55**, shows `pauseguard-sg.web.app` in the address bar, names Firebase, Firestore, Cloud Run and Gemini on screen, and has captions.
- [ ] `make deck VIDEO_URL=<the YouTube link>` re-run, so slide 14 carries the real video link; open the pptx once in PowerPoint or Google Slides and check slide 14.
- [ ] The repo on GitHub shows this README (push `main` and the `v1.0-submission` tag first).
- [ ] In the incognito window: pick Mrs Tan → Transfer → Prefill demo scenario → Review → Send → Use the demo answer → Check now → RED with boxes on the screenshot. Then sign in to `/console` and see her case.
- [ ] The deck, the README and the brief all quote the same numbers: recall 100% vs 78% (rules), false positives 4%, p50 7.6 s, US$0.0070 per check.

## After submitting: keep everything up and public until results are announced

The rules give **no retries or allowances** if anything is down during evaluation, and the evaluation dates are not published.

- Do **not** delete, rename, make private or transfer: the GitHub repo, the YouTube video, the Firebase site, the Cloud Run service `pauseguard-api`, the bucket, the BigQuery dataset or the GCP project `pauseguard-sg`.
- Keep billing on (budget alert only, never a cap). Watch the alert inbox (`make uptime ALERT_EMAIL=…`) for uptime and self-test alerts.
- The demo data resets itself every 6 hours (Cloud Scheduler) and a self-test runs daily at 07:30 SGT.
- On a known judging day or before the finale: `make deploy-api MIN_INSTANCES=1` (≈ US$2/day, no cold start), then back to `make deploy-api`.
- Re-check the four links from outside (incognito, mobile data) the day after submitting and then weekly.
- Fix only critical bugs during evaluation, on a branch, smoke-tested (`make smoke`), then redeploy; record the revision in `PROGRESS.md`.
