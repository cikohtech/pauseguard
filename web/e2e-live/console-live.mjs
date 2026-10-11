// The demo's two windows on the LIVE stack (phase 07 acceptance; `make console-live`).
// One browser: the console signs in as the demo analyst (Firestore listener), the customer app
// sends Mrs Tan's transfer with the demo answer (real Gemini), and the script measures when the
// case reaches the console relative to the customer's RED screen (target: within 1 s). Then the
// analyst presses S (Report as scam) and the watchlist must show the reported domain.
// Finally POST /admin/reset-demo clears the personas' checks and cases (ADMIN_TOKEN, API_URL).
//
//   node e2e-live/console-live.mjs [https://pauseguard-sg.web.app] [screenshot dir]
import { chromium } from 'playwright-core'

const SITE = process.argv[2] ?? 'https://pauseguard-sg.web.app'
const OUT = process.argv[3]
const { API_URL, ADMIN_TOKEN } = process.env
const log = (...a) => console.log(new Date().toISOString().slice(11, 23), ...a)
const fail = (msg) => {
  console.error(`✘ ${msg}`)
  process.exitCode = 1
}

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } })
const errors = []
try {
  const con = await ctx.newPage()
  con.on('pageerror', (e) => errors.push(`console: ${e}`))
  await con.goto(`${SITE}/console`)
  await con.getByRole('heading', { name: 'Analyst console' }).waitFor()
  await con.getByRole('button', { name: 'Sign in' }).click() // the demo login is prefilled
  await con.getByText('Live · Firestore').waitFor({ timeout: 30_000 })
  log('✔ console signed in as the demo analyst; queue is a Firestore listener')
  await con.evaluate(() => {
    window.__arrivals = {}
    const seen = new Set([...document.querySelectorAll('li[data-case-id]')].map((e) => e.dataset.caseId))
    new MutationObserver(() => {
      for (const li of document.querySelectorAll('li[data-case-id]')) {
        if (!seen.has(li.dataset.caseId)) {
          seen.add(li.dataset.caseId)
          window.__arrivals[li.dataset.caseId] = Date.now()
        }
      }
    }).observe(document.body, { childList: true, subtree: true })
  })

  const app = await ctx.newPage()
  app.on('pageerror', (e) => errors.push(`app: ${e}`))
  await app.goto(`${SITE}/app`)
  await app.getByRole('button', { name: /陈美玲女士|Mrs Tan/ }).click()
  await app.getByRole('link', { name: /^(Transfer|转账)/ }).first().click()
  await app.getByRole('button', { name: /Prefill demo scenario|填入演示情景/ }).click()
  await app.getByRole('button', { name: /Review transfer|核对转账/ }).click()
  await app.getByRole('button', { name: /^(Send|发送)/ }).click()
  const sheet = app.getByRole('dialog', { name: /Quick safety check|快速安全确认/ })
  await sheet.getByRole('button', { name: /使用演示答案|Use the demo answer/ }).click()
  await sheet.getByRole('img', { name: /WhatsApp_2026-10-11\.png/ }).waitFor()
  await sheet.getByRole('button', { name: /马上检查|Check now/ }).click()
  const tAnswer = Date.now()
  await app.getByTestId('verdict-RED').waitFor({ timeout: 90_000 })
  const tVerdict = Date.now()
  log(`✔ customer sees RED ${tVerdict - tAnswer} ms after answering`)
  if (OUT) await app.screenshot({ path: `${OUT}/live-app-red.png` })

  let arrival = null
  for (let i = 0; i < 50 && !arrival; i++) {
    const seen = Object.entries(await con.evaluate(() => window.__arrivals))
    if (seen.length) arrival = { id: seen[0][0], at: seen[0][1] }
    else await con.waitForTimeout(100)
  }
  if (!arrival) throw new Error('the case never reached the console')
  const delta = arrival.at - tVerdict
  log(`${delta <= 1000 ? '✔' : '✘'} case ${arrival.id} reached the console ${delta} ms after the customer's verdict (negative = before; target ≤ 1000)`)
  if (delta > 1000) fail('the case took more than 1 s')
  if (OUT) await con.screenshot({ path: `${OUT}/live-console-new-case.png` })

  await con.locator(`li[data-case-id="${arrival.id}"]`).getByRole('link').click()
  await con.getByTestId('case-view').getByText(arrival.id).waitFor()
  await con.getByRole('tab', { name: /Transaction risk/ }).click()
  await con.getByText(/Median payment S\$/).waitFor({ timeout: 15_000 })
  log('✔ risk tab:', await con.getByText(/Median payment S\$/).innerText())
  await con.locator('body').click({ position: { x: 5, y: 880 } }) // focus outside the note field
  await con.keyboard.press('s')
  const toast = con.getByText(/entit(y|ies) added to the watchlist/)
  await toast.waitFor({ timeout: 15_000 })
  log('✔ toast:', await toast.innerText())
  await con.getByRole('link', { name: 'Watchlist' }).click()
  const row = con.locator('tr', { hasText: 'mas-gov-verify.example' })
  await row.waitFor({ timeout: 15_000 })
  const text = (await row.innerText()).replace(/\s+/g, ' ')
  if (text.includes('Analyst report')) log('✔ watchlist:', text)
  else fail(`watchlist row not reported by an analyst: ${text}`)
  if (OUT) await con.screenshot({ path: `${OUT}/live-console-watchlist.png` })
  if (errors.length) fail(`page errors: ${errors.join(' | ')}`)
} catch (err) {
  fail(String(err))
} finally {
  await browser.close()
  if (API_URL && ADMIN_TOKEN) {
    const res = await fetch(`${API_URL}/api/v1/admin/reset-demo`, { method: 'POST', headers: { 'X-Admin-Token': ADMIN_TOKEN } })
    log('reset-demo:', res.status, await res.text())
  } else {
    log('ℹ no API_URL/ADMIN_TOKEN: demo data not reset')
  }
}
