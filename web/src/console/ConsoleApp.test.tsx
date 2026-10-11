// The console end to end in jsdom, against a fake API (local mode: no Firebase config, so the
// queue polls GET /cases every second instead of the Firestore listener).
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { AppRoutes } from '@/App'
import type { CaseSummary } from '@/console/api'
import { METRICS, NEW_CASE, QUEUE, TAN_DETAIL, WATCHLIST } from '@/test/consoleFixtures'

type Route = (body: unknown) => unknown
const calls: { method: string; path: string; body: unknown }[] = []

function fakeApi(routes: Record<string, Route>) {
  calls.length = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const u = new URL(url)
      const path = u.pathname.replace('/api/v1', '') + u.search
      const body = init?.body ? JSON.parse(init.body as string) : null
      calls.push({ method, path, body })
      const key = Object.keys(routes).find((k) => new RegExp(`^${k}$`).test(`${method} ${path}`))
      if (!key) return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: path } }), { status: 404 })
      return new Response(JSON.stringify(routes[key](body)), { status: 200 })
    }),
  )
}

// Recharts' ResponsiveContainer measures its parent; jsdom has no layout engine.
class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal('ResizeObserver', FakeResizeObserver)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )

test('the queue lists RED first, and a case that arrives later slides in as new', async () => {
  let queue: CaseSummary[] = QUEUE
  fakeApi({ 'GET /cases\\?status=OPEN&limit=100': () => queue })
  renderAt('/console')

  const list = await screen.findByRole('list', { name: 'Open cases, RED first' })
  const rows = within(list).getAllByRole('link')
  expect(rows.map((r) => r.textContent)).toEqual([
    expect.stringMatching(/^RED.*Tan Mei Ling, 67S\$8,000.*Government impersonation/),
    expect.stringMatching(/^AMBER.*Raj Kumar, 29S\$450.*Job \/ task scam/),
  ])
  expect(rows[0]).toHaveAttribute('href', '/console/cases/case_tan')
  expect(screen.getByText('Live · polling')).toBeInTheDocument()
  expect(screen.queryByText('New')).not.toBeInTheDocument() // nothing is "new" on the first load

  queue = [...QUEUE, NEW_CASE]
  const fresh = await screen.findByText('New', {}, { timeout: 3000 })
  expect(fresh.closest('li')).toHaveAttribute('data-case-id', 'case_new')
  expect(screen.getByText('New RED case: Nur Aisyah, S$2,400')).toBeInTheDocument() // aria-live
})

test('an empty queue says how to make a case', async () => {
  fakeApi({ 'GET /cases\\?status=OPEN&limit=100': () => [] })
  renderAt('/console')
  expect(await screen.findByText('No open cases')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Make one in the customer app/ })).toHaveAttribute('href', '/app')
})

function caseRoutes(onDecide: Route = () => ({ case_id: 'case_tan', status: 'REPORTED', watchlist_added: 3 })) {
  return {
    'GET /cases\\?status=OPEN&limit=100': () => QUEUE,
    'GET /cases/case_tan': () => TAN_DETAIL,
    'GET /cases/case_tan/history': () => ({
      customer_id: 'cust_001',
      as_of: '2026-10-11T06:00:00Z',
      days: [{ day: '2026-10-10', amount: 120, count: 2 }],
      median_debit_90d: 60,
      transfer_amount: 8000,
    }),
    'POST /cases/case_tan/decision': onDecide,
  }
}

test('the case view shows the case file, tabs and the recommended action', async () => {
  fakeApi(caseRoutes())
  renderAt('/console/cases/case_tan')

  expect(await screen.findByRole('heading', { name: 'MAS officer impersonation, S$8,000 to a new payee' })).toBeInTheDocument()
  const view = screen.getByTestId('case-view')
  expect(within(view).getAllByText('Report as scam').length).toBeGreaterThan(0)
  expect(within(view).getByText(/Classic government-impersonation pattern/)).toBeInTheDocument() // Summary card
  expect(screen.getByText('Payee phone on the watchlist (hard stop)')).toBeInTheDocument() // fusion reasons
  expect(screen.getByRole('link', { name: /All open cases/ })).toBeInTheDocument()

  await userEvent.click(screen.getByRole('tab', { name: /Evidence/ }))
  expect(screen.getByRole('img', { name: 'Customer upload chat.png, with 2 flags marked' })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Flag 1: “Safe account”' })).toBeInTheDocument()
  const entities = screen.getByRole('list', { name: 'Extracted entities' })
  expect(within(entities).getAllByText('on watchlist')).toHaveLength(2)
  expect(within(entities).getByText('payee')).toBeInTheDocument()

  await userEvent.click(screen.getByRole('tab', { name: /Transaction risk/ }))
  expect(screen.getByRole('img', { name: 'Transaction risk score 85 of 100, high' })).toBeInTheDocument()
  expect(screen.getByText('28.4×')).toBeInTheDocument()
  expect(await screen.findByText(/Median payment S\$60; this transfer is 28.4× that/)).toBeInTheDocument()

  await userEvent.click(screen.getByRole('tab', { name: /Intel/ }))
  expect(screen.getByText('MAS warns that it never asks the public to transfer money.')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Source 1/ })).toHaveAttribute('target', '_blank')
  expect(screen.getByTitle('Google Search suggestions')).toHaveAttribute('sandbox', 'allow-popups allow-popups-to-escape-sandbox')

  await userEvent.click(screen.getByRole('tab', { name: /Audit/ }))
  expect(screen.getByText('Called the customer')).toBeInTheDocument()
})

test('pressing S reports the scam with the note and shows the watchlist toast', async () => {
  fakeApi(caseRoutes())
  renderAt('/console/cases/case_tan')
  await screen.findByTestId('case-view')

  // typing in the note never triggers a shortcut
  await userEvent.type(screen.getByRole('textbox', { name: /Note for the audit log/ }), 'Confirmed with son')
  expect(calls.some((c) => c.method === 'POST')).toBe(false)

  await userEvent.click(document.body)
  await userEvent.keyboard('s')
  expect(await screen.findByText('Reported as scam')).toBeInTheDocument()
  expect(screen.getByText('3 entities added to the watchlist')).toBeInTheDocument()
  const post = calls.find((c) => c.method === 'POST')
  expect(post).toEqual({
    method: 'POST',
    path: '/cases/case_tan/decision',
    body: { action: 'REPORT_SCAM', note: 'Confirmed with son' },
  })
})

test('releasing a RED case asks first, and "Keep it held" sends nothing', async () => {
  fakeApi(caseRoutes(() => ({ case_id: 'case_tan', status: 'RELEASED', watchlist_added: 0 })))
  renderAt('/console/cases/case_tan')
  await screen.findByTestId('case-view')

  await userEvent.click(screen.getByRole('button', { name: 'Release' }))
  const dialog = await screen.findByRole('dialog', { name: /Release this held payment/ })
  await userEvent.click(within(dialog).getByRole('button', { name: 'Keep it held' }))
  expect(calls.some((c) => c.method === 'POST')).toBe(false)

  await userEvent.keyboard('r')
  await userEvent.click(await screen.findByRole('button', { name: 'Release payment' }))
  expect(await screen.findByText('Payment released')).toBeInTheDocument()
  expect(calls.filter((c) => c.method === 'POST')).toHaveLength(1)
})

test('the dashboard shows the KPI tiles and switches range', async () => {
  fakeApi({ 'GET /metrics\\?range=(today|7d)': () => METRICS })
  renderAt('/console/dashboard')
  const kpis = await screen.findByTestId('kpis')
  expect(within(kpis).getByText('S$8,450')).toBeInTheDocument()
  expect(within(kpis).getByText('1 · 1 · 1')).toBeInTheDocument()
  expect(within(kpis).getByText('5.2 s / 8.8 s')).toBeInTheDocument()
  expect(within(kpis).getByText('Not priced')).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: 'Table view of Verdicts over time' }))
  expect(screen.getByRole('columnheader', { name: 'Hour' })).toBeInTheDocument()

  await userEvent.click(screen.getByRole('button', { name: 'Last 7 days' }))
  await waitFor(() => expect(calls.some((c) => c.path === '/metrics?range=7d')).toBe(true))
  expect(await screen.findByText('Money protected in 7 days')).toBeInTheDocument()
})

test('the watchlist marks fresh analyst reports and filters as you type', async () => {
  fakeApi({ 'GET /watchlist\\?limit=500': () => WATCHLIST })
  renderAt('/console/watchlist')
  const table = await screen.findByRole('table')
  await waitFor(() => expect(within(table).getAllByRole('row')).toHaveLength(3))
  expect(within(table).getByText('New')).toBeInTheDocument()
  expect(screen.getByText(/2 entries, 1 from analyst reports/)).toBeInTheDocument()

  await userEvent.type(screen.getByRole('searchbox', { name: 'Search the watchlist' }), '8000 0147')
  expect(within(table).getAllByRole('row')).toHaveLength(2)
  expect(within(table).getByText('+6580000147')).toBeInTheDocument()

  await act(async () => {
    await userEvent.clear(screen.getByRole('searchbox', { name: 'Search the watchlist' }))
  })
  await userEvent.click(screen.getByRole('button', { name: 'Domain' }))
  expect(within(table).getAllByRole('row')).toHaveLength(2)
})

test('the console login is prefilled with the demo analyst and says local dev has no sign-in', async () => {
  fakeApi({})
  renderAt('/console/login')
  expect(await screen.findByRole('heading', { name: 'Analyst console' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Open the console/ })).toHaveAttribute('href', '/console')
})
