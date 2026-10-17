// Deck and README screenshots from the LIVE stack (phase 11; `make screens`).
// Real Gemini, real Firebase Auth and Firestore: nothing is mocked. It runs Raj (AMBER) and Mrs Tan
// (RED, recorded for the README GIF) in the customer app on a phone viewport, then signs in to the console as the demo analyst and captures the queue, Mrs Tan's
// case (summary, evidence, risk, intel) and the dashboard. Finally POST /admin/reset-demo clears the
// personas' checks and cases (ADMIN_TOKEN, API_URL), as `make console-live` does.
//
//   node e2e-live/screens.mjs [https://pauseguard-sg.web.app] [out dir] [video dir]
import { chromium, devices } from 'playwright-core'

const SITE = process.argv[2] ?? 'https://pauseguard-sg.web.app'
const OUT = process.argv[3] ?? '../docs/img/screens'
const VIDEO = process.argv[4]
const { API_URL, ADMIN_TOKEN } = process.env
const log = (...a) => console.log(new Date().toISOString().slice(11, 19), ...a)
const pause = (page, ms = 700) => page.waitForTimeout(ms) // so the recording is watchable
const phone = { ...devices['iPhone 13'], deviceScaleFactor: 3 }

async function resetDemo() {
  if (!API_URL || !ADMIN_TOKEN) return log('ℹ no API_URL/ADMIN_TOKEN: demo data not reset')
  const res = await fetch(`${API_URL}/api/v1/admin/reset-demo`, { method: 'POST', headers: { 'X-Admin-Token': ADMIN_TOKEN } })
  log('reset-demo:', res.status)
}

async function wakeApi() {
  if (!API_URL) return
  const t = Date.now()
  const res = await fetch(`${API_URL}/health`)
  log(`/health ${res.status} in ${Date.now() - t} ms`)
}

// One customer transfer, from the persona picker to the verdict. Returns the page on the verdict.
async function transfer(browser, { persona, verdict, shots, record }) {
  const ctx = await browser.newContext({ ...phone, ...(record ? { recordVideo: { dir: VIDEO, size: { width: 390, height: 844 } } } : {}) })
  const page = await ctx.newPage()
  await page.goto(`${SITE}/app`)
  await page.getByRole('button', { name: persona }).waitFor()
  await pause(page, 1200)
  if (shots.picker) await page.screenshot({ path: `${OUT}/${shots.picker}` })
  await page.getByRole('button', { name: persona }).click()
  await pause(page)
  await page.getByRole('link', { name: /^Transfer/ }).first().click()
  await pause(page)
  await page.getByRole('button', { name: 'Prefill demo scenario' }).click()
  await pause(page)
  await page.getByRole('button', { name: 'Review transfer' }).click()
  await pause(page)
  await page.getByRole('button', { name: /^Send/ }).click()
  const sheet = page.getByRole('dialog', { name: 'Quick safety check' })
  await sheet.waitFor()
  await pause(page)
  await sheet.getByRole('button', { name: 'Use the demo answer' }).click()
  await pause(page, 1200)
  if (shots.checkin) await page.screenshot({ path: `${OUT}/${shots.checkin}` })
  await sheet.getByRole('button', { name: 'Check now' }).click()
  const t = Date.now()
  await page.getByTestId('analysing').waitFor()
  await pause(page, 2500)
  if (shots.analysing) await page.screenshot({ path: `${OUT}/${shots.analysing}` })
  await page.getByTestId(/^verdict-/).waitFor({ timeout: 90_000 })
  const got = (await page.getByTestId(/^verdict-/).getAttribute('data-testid')).replace('verdict-', '')
  const boxes = await page.getByTestId(/^flag-box-/).count()
  log(`${got === verdict ? '✔' : '✘'} ${String(persona)}: ${got} in ${Date.now() - t} ms, ${boxes} boxes on the screenshot`)
  await pause(page, 2000)
  if (shots.verdict) {
    await page.screenshot({ path: `${OUT}/${shots.verdict}` })
    await page.screenshot({ path: `${OUT}/${shots.verdict.replace('.png', '-full.png')}`, fullPage: true })
  }
  // The evidence card, scrolled into view (the numbered boxes and their explanations).
  if (shots.evidence) {
    const card = page.locator('section[aria-labelledby]').filter({ has: page.locator('h2') }).first()
    if (await card.count()) await card.evaluate((el) => el.scrollIntoView({ block: 'start' }))
    await pause(page, 800)
    await page.screenshot({ path: `${OUT}/${shots.evidence}` })
  }
  await pause(page, 1500)
  const video = record ? page.video() : null
  await ctx.close()
  if (video) log('video:', await video.path())
  return { verdict: got, boxes }
}

const browser = await chromium.launch()
let ok = true
try {
  await resetDemo()
  await wakeApi()

  // Raj first, then Tan, so Mrs Tan's case is the newest RED at the top of the queue.
  const raj = await transfer(browser, {
    persona: 'Continue as Raj Kumar',
    verdict: 'AMBER',
    shots: { verdict: '03-amber.png', evidence: '03-amber-evidence.png' },
  })
  const tan = await transfer(browser, {
    persona: /Mrs Tan/,
    verdict: 'RED',
    record: Boolean(VIDEO),
    shots: {
      picker: '01-persona-picker.png',
      checkin: '02-checkin.png',
      analysing: '02-analysing.png',
      verdict: '04-red.png',
      evidence: '04-red-evidence.png',
    },
  })
  ok = raj.verdict === 'AMBER' && tan.verdict === 'RED' && tan.boxes > 0

  // The analyst console on a desktop.
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 })
  const con = await ctx.newPage()
  await con.goto(SITE)
  await con.getByRole('heading', { name: 'Pause before you pay.' }).waitFor()
  await pause(con, 1500)
  await con.screenshot({ path: `${OUT}/00-landing.png` })
  await con.goto(`${SITE}/console`)
  await con.getByRole('button', { name: 'Sign in' }).click() // the demo login is prefilled
  await con.getByText('Live · Firestore').waitFor({ timeout: 30_000 })
  const first = con.locator('li[data-case-id]').first()
  await first.waitFor()
  await first.getByRole('link').click()
  const view = con.getByTestId('case-view')
  await view.waitFor()
  await con.getByRole('status', { name: 'Writing the case file' }).waitFor({ state: 'detached', timeout: 60_000 })
  await pause(con, 1500)
  await con.screenshot({ path: `${OUT}/05-console-case.png` })
  for (const [tab, file, ready] of [
    [/Evidence/, '05-console-evidence.png', () => con.getByRole('button', { name: /^Flag 1/ }).first().waitFor()],
    [/Transaction risk/, '05-console-risk.png', () => con.getByText(/Median payment S\$/).waitFor({ timeout: 20_000 })],
    [/Intel/, '05-console-intel.png', () => con.waitForTimeout(1500)],
  ]) {
    await con.getByRole('tab', { name: tab }).click()
    await ready()
    await pause(con, 1200)
    await con.screenshot({ path: `${OUT}/${file}` })
  }
  await con.getByRole('link', { name: 'Dashboard' }).click()
  await con.getByTestId('kpis').waitFor()
  await pause(con, 3000) // the charts animate in
  await con.screenshot({ path: `${OUT}/06-dashboard.png` })
  await ctx.close()
  log(ok ? '✔ all screens captured' : '✘ a verdict was not the expected one: check the screenshots before using them')
} catch (err) {
  ok = false
  console.error(`✘ ${err}`)
} finally {
  await browser.close()
  await resetDemo()
  process.exitCode = ok ? 0 : 1
}
