// The landing page and the analyst console (/console) in Chromium, API mocked at the network
// layer (local mode: no Firebase config, so the queue polls GET /cases). axe (WCAG 2.1 A + AA)
// on every screen and tab, the Release confirm dialog, the R/H/E/S shortcuts and a keyboard-only
// run. Screenshots land in test-results/screens/.
import { readFileSync } from 'node:fs'

import { expect, test, type Page } from '@playwright/test'

import { METRICS, NEW_CASE, QUEUE, TAN_DETAIL, WATCHLIST } from '../src/test/consoleFixtures'
import { scan } from './axe'
import { API } from './fixtures'

const TAN_PNG = readFileSync(new URL('../public/demo/tan_mas_chat.png', import.meta.url))

interface ConsoleApi {
  decisions: { action: string; note: string | null }[]
  addCase: () => void
}

async function consoleApi(page: Page): Promise<ConsoleApi> {
  const state: ConsoleApi & { queue: typeof QUEUE } = {
    decisions: [],
    queue: [...QUEUE],
    addCase: () => {
      state.queue = [...state.queue, NEW_CASE]
    },
  }
  const json = (body: unknown) => ({ status: 200, contentType: 'application/json', body: JSON.stringify(body) })
  await page.route('https://storage.example/**', (route) => route.fulfill({ status: 200, contentType: 'image/png', body: TAN_PNG }))
  await page.route(`${API}/**`, async (route) => {
    const url = new URL(route.request().url())
    const path = url.pathname.replace('/api/v1', '')
    const method = route.request().method()
    if (method === 'GET' && path === '/cases') return route.fulfill(json(state.queue))
    if (method === 'GET' && path === '/cases/case_tan') return route.fulfill(json(TAN_DETAIL))
    if (method === 'GET' && path === '/cases/case_tan/history') {
      const days = Array.from({ length: 91 }, (_, i) => {
        const d = new Date(Date.UTC(2026, 6, 12 + i))
        return { day: d.toISOString().slice(0, 10), amount: i % 3 === 0 ? 40 + (i % 7) * 12 : 0, count: i % 3 === 0 ? 1 : 0 }
      })
      return route.fulfill(json({ customer_id: 'cust_001', as_of: '2026-10-11T06:00:00Z', days, median_debit_90d: 43.5, transfer_amount: 8000 }))
    }
    if (method === 'POST' && path === '/cases/case_tan/decision') {
      const body = route.request().postDataJSON() as { action: string; note: string | null }
      state.decisions.push(body)
      const status = { RELEASE: 'RELEASED', HOLD: 'HELD', ESCALATE: 'ESCALATED', REPORT_SCAM: 'REPORTED' }[body.action]
      return route.fulfill(json({ case_id: 'case_tan', status, watchlist_added: body.action === 'REPORT_SCAM' ? 3 : 0 }))
    }
    if (method === 'GET' && path === '/metrics') return route.fulfill(json(METRICS))
    if (method === 'GET' && path === '/watchlist') return route.fulfill(json(WATCHLIST))
    return route.fulfill({ status: 404, contentType: 'application/json', body: '{"error":{"code":"NOT_FOUND","message":"x"}}' })
  })
  return state
}

test('landing page: the pitch, the source, both entry points, in English only', async ({ page }) => {
  await page.goto('/')
  await expect(page.getByRole('heading', { name: 'Pause before you pay.' })).toBeVisible()
  await expect(page.getByText('81.8%')).toBeVisible()
  await expect(page.getByRole('link', { name: /Try the customer app/ })).toBeVisible()
  await expect(page.getByRole('link', { name: /Open the analyst console/ })).toBeVisible()
  await expect(page.getByRole('button', { name: /Language/ })).toHaveCount(0)
  await scan(page, 'landing')
})

test('console login (local dev: sign-in off)', async ({ page }) => {
  await consoleApi(page)
  await page.goto('/console/login')
  await expect(page.getByRole('heading', { name: 'Analyst console' })).toBeVisible()
  await scan(page, 'console-login')
})

test('queue: RED first, and a new case slides in', async ({ page }) => {
  const api = await consoleApi(page)
  await page.goto('/console')
  const rows = page.getByRole('list', { name: 'Open cases, RED first' }).getByRole('listitem')
  await expect(rows).toHaveCount(2)
  await expect(rows.first()).toHaveAttribute('data-verdict', 'RED')
  api.addCase()
  await expect(page.locator('[data-case-id=case_new]')).toBeVisible({ timeout: 3000 })
  await expect(page.locator('[data-case-id=case_new]')).toContainText('New')
  await scan(page, 'console-queue')
})

test('case view: every tab, the evidence boxes and the risk chart pass axe', async ({ page }) => {
  await consoleApi(page)
  await page.goto('/console/cases/case_tan')
  await expect(page.getByRole('heading', { name: TAN_DETAIL.case.case_file!.title })).toBeVisible()
  await scan(page, 'console-case-summary')

  await page.getByRole('tab', { name: /Evidence/ }).click()
  const img = page.getByRole('img', { name: /Customer upload chat.png/ })
  await expect(img).toBeVisible()
  // Box 1 sits at box_2d [410, 60, 470, 940] of the rendered image.
  const imgBox = (await img.boundingBox())!
  const box = (await page.getByRole('button', { name: 'Flag 1: “Safe account”' }).boundingBox())!
  expect(Math.abs(box.y - (imgBox.y + 0.41 * imgBox.height))).toBeLessThan(3)
  expect(Math.abs(box.x - (imgBox.x + 0.06 * imgBox.width))).toBeLessThan(3)
  await scan(page, 'console-case-evidence')

  await page.getByRole('tab', { name: /Transaction risk/ }).click()
  await expect(page.getByText('S$8,000', { exact: true }).last()).toBeVisible() // the spike's label
  await scan(page, 'console-case-risk')
  await page.getByRole('tab', { name: /Intel/ }).click()
  await expect(page.getByTitle('Google Search suggestions')).toBeVisible()
  await scan(page, 'console-case-intel')
  await page.getByRole('tab', { name: /Audit/ }).click()
  await scan(page, 'console-case-audit')
})

test('actions: S reports with the note; R on a RED case asks first', async ({ page }) => {
  const api = await consoleApi(page)
  await page.goto('/console/cases/case_tan')
  await expect(page.getByTestId('case-view')).toBeVisible()

  await page.getByRole('button', { name: 'Release' }).click()
  const dialog = page.getByRole('dialog', { name: /Release this held payment/ })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Keep it held' })).toBeFocused()
  await scan(page, 'console-release-confirm')
  await page.keyboard.press('Escape')
  await expect(dialog).toBeHidden()

  const note = page.getByRole('textbox', { name: /Note for the audit log/ })
  await note.fill('Spoke to her son')
  await page.keyboard.press('s') // in the note field the key types a letter, it is no shortcut
  await expect(note).toHaveValue('Spoke to her sons')
  expect(api.decisions).toEqual([])
  await note.press('Escape') // leaves the field
  await page.keyboard.press('s')
  await expect(page.getByText('3 entities added to the watchlist')).toBeVisible()
  expect(api.decisions).toEqual([{ action: 'REPORT_SCAM', note: 'Spoke to her sons' }])
})

test('dashboard and watchlist pass axe; the table views work', async ({ page }) => {
  await consoleApi(page)
  await page.goto('/console/dashboard')
  await expect(page.getByTestId('kpis')).toContainText('S$8,450')
  await scan(page, 'console-dashboard')
  await page.getByRole('button', { name: 'Table view of Latency' }).click()
  await expect(page.getByRole('cell', { name: '20 s+' })).toBeVisible()
  await scan(page, 'console-dashboard-table')

  await page.goto('/console/watchlist')
  await expect(page.getByRole('table')).toContainText('mas-gov-verify.example')
  await page.getByRole('searchbox', { name: 'Search the watchlist' }).fill('8000 0147')
  await expect(page.getByRole('table').getByRole('row')).toHaveCount(2)
  await scan(page, 'console-watchlist')
})

test('keyboard only: open a case from the queue, switch tabs, hold it', async ({ page }, info) => {
  test.skip(info.project.name === 'phone', 'the console is keyboard-first on desktop')
  const api = await consoleApi(page)
  await page.goto('/console/watchlist')
  await page.getByRole('link', { name: 'Queue' }).focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/console\/cases\/case_tan$/) // the top (RED) case opens itself
  // Tab from the queue's sound toggle to the first row, then to the case's tabs.
  await page.getByRole('button', { name: 'Sound for new cases' }).focus()
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: /Tan Mei Ling/ })).toBeFocused()
  await page.keyboard.press('Enter')
  await page.getByRole('tab', { name: /Summary/ }).focus()
  await page.keyboard.press('ArrowRight')
  await expect(page.getByRole('tab', { name: /Evidence/ })).toBeFocused()
  await expect(page.getByRole('tab', { name: /Evidence/ })).toHaveAttribute('aria-selected', 'true')
  await page.keyboard.press('h')
  await expect(page.getByText('Payment held')).toBeVisible()
  expect(api.decisions).toEqual([{ action: 'HOLD', note: null }])
})
