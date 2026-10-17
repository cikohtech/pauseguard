# UI Spec: PauseGuard

One React app, two areas. **Best UI/UX is a $2,000 prize**, so polish matters. The look should be calm, trustworthy and modern: a bank, not a hacker tool.

## Design system

Redesigned on 17 Oct 2026 (DECISIONS): **Material 3** throughout, in two schemes that share one set of role tokens (`web/src/index.css`), so every component is written once.

- **Tone:** reassuring, never alarming or blaming. Verdict colours are used sparingly; everything else is neutral.
- **Two schemes:**
  - **Harbour Bank (customer app, inside the phone):** Material You, `SchemeTonalSpot` generated with `material-color-utilities` from the harbour-teal seed `#0F5E6E` (primary `#00687A`, surface `#F5FAFC`). Scoped to `[data-phone]`, so the check-in sheet and dialogs (which portal into the phone) inherit it.
  - **Google (landing page, the demo stage, the analyst console):** Google's own Material 3 ("GM3": Gmail, Drive, the Cloud console): primary `#0B57D0`, surface `#F8FAFD`, the work on a white rounded panel, secondary-container `#C2E7FF` for selection.
  - **Verdicts:** GREEN / AMBER / RED each have a solid, an ink (text, AA on white and on the soft tint) and a soft container. Bank: M3 custom colours from `#1F8A5B` / `#B7791F` plus the scheme's error role. Google: the Cloud console status colours (`#1E8E3E`, `#E37400`, `#D93025`; inks `#137333`, `#9A5500`, `#C5221F`). Always pair colour with an icon **and** a word, and in the customer app also a shape (below), never colour alone.
- **Type:** Google Sans (variable, OFL) for Latin, Noto Sans SC for Chinese, Google Sans Code for IDs and account numbers. The M3 type scale is a set of Tailwind utilities (`text-display-l` … `text-label-s`). Base 16px in the app.
- **Shape and motion:** M3 shape scale (4 → 48px; pills for buttons and chips, 28px sheets and dialogs). M3 Expressive shapes (cookie, sunny, burst; `components/m3/shapes.ts`) carry the verdict hero (GREEN sunny, AMBER 6-point cookie, RED 12-point cookie), the morphing loading indicator while the check runs, and a wavy progress bar for GREEN's 2-second auto-continue. Emphasized easing and a spring for the verdict; everything honours `prefers-reduced-motion`.
- **Components:** M3 buttons (filled, tonal, outlined, text), icon buttons, filter and assist chips, outlined text fields with floating labels, connected list groups, navigation bar (app), navigation drawer + rail and top app bar with search (console), primary tabs, segmented buttons, bottom sheet, basic dialog, snackbar (sonner, styled). Every pressable surface has an M3 state layer and a ripple (`lib/ripple.ts`). shadcn/ui (radix) still provides Dialog and Tabs behaviour.
- **Icons:** Material Symbols (Apache-2.0) as inline SVG, Rounded in the app and on the landing page, Outlined in the console; only the icons we use ship (`web/scripts/gen-icons.mjs`).
- **AI labelling:** what Gemini wrote (case summary, recommended action) carries a gradient sparkle and a "Written by Gemini" label, the way Google products label AI output; the deterministic verdict reasons are labelled "Rules, not AI".
- **Motion:** subtle. The analysis progress uses step ticks ("Reading the message ✓ · Checking the payee ✓ · Comparing with known scams …"), never a bare spinner.
- **Accessibility:** WCAG 2.1 AA contrast (every token pair checked), 44px+ tap targets, a 3px M3 focus ring on everything, `aria-live` for verdict announcements, full keyboard support in the console, alt text on evidence previews. `make a11y` runs axe on every screen, desktop and phone.
- **i18n:** `react-i18next` with `en` and `zh` in the MVP (`ms` and `ta` stretch). All customer strings are in locale files, and the language switcher sits in the header.

## Area 1: `/app` customer banking mock (mobile frame)

On desktop, render inside a 390×844 phone frame (an Android device in the Pixel style), centred, with a caption beside it: what the demo is, the persona you are playing, a four-step "try it" guide, a link to the console, and the live API status. On mobile, use the full screen.

**Screens**
1. **Persona picker** (demo only): three cards (Mrs Tan / Raj / Aisyah) with a one-line story. It sets `customer_id` and language.
2. **Home:** balance card, recent transactions, a big "Transfer" button. Fictional "Harbour Bank" logo (simple wordmark).
3. **Transfer form:** payee (pick saved or "New payee": name, bank, account), amount, note. "Prefill demo scenario" link for the video.
4. **Review & confirm:** standard bank confirm screen → tap "Send".
5. **Check-in sheet** (bottom sheet, triggered if needed):
   - Header: PauseGuard shield icon + "Quick safety check" + "Takes about 10 seconds".
   - The question, quick-reply chips, a free-text box, a mic button (stretch), and "Add a screenshot or file" (camera/gallery/file).
   - Thumbnail previews of uploads; "Check now" button.
6. **Analysing:** step-tick progress (from the SSE events).
7. **Verdict screens:**
   - **GREEN:** green check, "Looks good. Your transfer is on its way." Auto-continue after 2 s.
   - **AMBER:** amber shield, headline, short body, and the **evidence card**: the uploaded screenshot with flag boxes drawn on it (convert `box_2d` 0–1000 to percentages; numbered markers 1–4), and below it the numbered explanations. Buttons: **"Pause for 24 hours" (primary)**, "Call my son/daughter (trusted contact)", and a quiet text button "I understand the risk, continue", which opens a confirm dialog.
   - **RED:** red shield, "We've paused this transfer to protect you." The same evidence card. "Our fraud team will call you within 30 minutes on your registered number. Never share OTPs." Buttons: "Call my trusted contact", "Call 1799 anti-scam helpline". No proceed option.
   - All verdicts have a small "Was this helpful? 👍 👎".
8. **Senior mode** (stretch): toggle in settings → larger type, simpler layout, voice playback of the explanation (TTS).

## Area 2: `/console` analyst console (desktop)

Login (Firebase email/password, seeded analyst account), then:

1. **Queue (left, 360px):** realtime list of OPEN cases sorted by verdict (RED first) then time. Each row shows the verdict badge, customer name and age, amount, typology chip and how long ago. A new case animates in with a subtle highlight and a sound toggle.
2. **Case view (main):**
   - Header: verdict, amount, payee, typology + confidence bar, recommended action.
   - Tabs:
     - **Summary:** case-file summary, timeline, recommended action with reason.
     - **Evidence:** the evidence image(s) with flag overlays, extracted entities as chips (phone, URL, account), raw text.
     - **Transaction risk:** score gauge, feature table with points, and a 90-day mini chart of the customer's outgoing amounts with this one highlighted.
     - **Intel:** watchlist matches, web findings with source links.
     - **Audit:** history.
   - Action bar (sticky bottom): **Release · Hold · Escalate · Report as scam**, with keyboard shortcuts R/H/E/S, a note field and a confirm toast.
3. **Dashboard** (`/console/dashboard`): KPI tiles (checks today, money protected, RED/AMBER/GREEN split, false-positive rate, p50/p95 latency, cost per check) and charts (verdicts over time, top typologies, latency histogram). Use Recharts and keep it simple and readable.
4. **Watchlist** (`/console/watchlist`): a searchable table of entries with source and reported count.

## Area 3: landing page `/`

A one-screen pitch for judges who open the live link: headline, the 82% stat with its source, three steps (Check, Explain, Protect), and two big buttons, "Try the customer app" and "Open the analyst console (demo login prefilled)". Footer: "Prototype for the Google Cloud AI Builder Cup 2026 · Built on Gemini, ADK, Cloud Run, BigQuery, Firestore · All data synthetic".

## Wireframes for the deck

In phase 11, capture screenshots of: persona picker, check-in sheet, AMBER evidence card, RED screen, console case view, dashboard. Save them to `docs/img/screens/`.
