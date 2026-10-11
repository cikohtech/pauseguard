import { act, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'

import i18n from '@/i18n'
import { SessionProvider } from '@/customer/SessionProvider'
import { Verdict } from '@/customer/screens/Verdict'
import type { CheckState } from '@/customer/session'
import type { CheckResult, Transfer, Verdict as VerdictKind } from '@/lib/api'

const transfer: Transfer = {
  payee_name: 'Lee Wei Investigation Acct',
  account_number: '123-45678-9',
  bank_name: 'Harbour Bank',
  dest_type: 'LOCAL_BANK',
  amount: 8000,
  currency: 'SGD',
  note: 'case 2231',
}

function result(verdict: VerdictKind, over: Partial<CheckResult> = {}): CheckResult {
  const flagged = verdict !== 'GREEN'
  return {
    check_id: 'chk_TEST0001',
    status: 'DONE',
    verdict,
    action: { GREEN: 'PROCEED', AMBER: 'COOL_OFF', RED: 'HOLD_FOR_REVIEW' }[verdict] as CheckResult['action'],
    needs_review: false,
    typology: flagged ? 'GOV_OFFICIAL_IMPERSONATION' : 'NONE',
    confidence: 0.95,
    top_flags: flagged
      ? [{ code: 'SAFE_ACCOUNT', severity: 'HIGH', quote: 'safe account', evidence_index: 0, box_2d: [400, 50, 480, 900] }]
      : [],
    customer_message: {
      language: 'en',
      headline: { GREEN: 'Looks good', AMBER: "Let's pause and check this payment", RED: "We've paused this transfer to protect you" }[verdict],
      body: { GREEN: 'Your transfer is on its way.', AMBER: 'This looks like a known scam.', RED: 'This payment shows clear signs of a scam.' }[verdict],
      flag_explanations: flagged ? [{ code: 'SAFE_ACCOUNT', text: "There is no such thing as a 'safe account'." }] : [],
      next_steps: [],
    },
    case_id: flagged ? 'case_TEST' : null,
    latency_ms: { total: 4200 },
    ...over,
  }
}

const fetchMock = vi.fn()

function renderVerdict(r: CheckResult) {
  const check: CheckState = {
    id: r.check_id,
    question: { text: 'Who asked you to make this payment?', quick_replies: [] },
    fastVerdict: null,
    result: r,
    evidence: [{ kind: 'image', name: 'chat.png', url: 'blob:chat' }],
  }
  return render(
    <MemoryRouter initialEntries={['/app/verdict']}>
      <SessionProvider initial={{ personaId: 'cust_001', transfer, check }}>
        <Routes>
          <Route path="/app/verdict" element={<Verdict />} />
          <Route path="/app/done" element={<p>outcome screen</p>} />
          <Route path="/app/home" element={<p>home screen</p>} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  )
}

const choiceCalls = () =>
  fetchMock.mock.calls
    .filter(([url]) => String(url).endsWith('/choice'))
    .map(([, init]) => JSON.parse((init as RequestInit).body as string))

beforeEach(async () => {
  await i18n.changeLanguage('en')
  fetchMock.mockReset()
  fetchMock.mockResolvedValue(new Response(JSON.stringify({ check_id: 'chk_TEST0001', customer_choice: 'X' })))
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

test('RED: held, fraud-team notice, evidence card, call buttons and no way to proceed', () => {
  renderVerdict(result('RED'))
  expect(screen.getByRole('heading', { level: 1, name: "We've paused this transfer to protect you" })).toHaveFocus()
  expect(screen.getByText('On hold')).toBeInTheDocument() // the verdict as a word, not colour alone
  expect(screen.getByText(/fraud team will call you within 30 minutes/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /Warning sign 1: “Safe account”/ })).toBeInTheDocument()

  expect(screen.getByRole('link', { name: 'Call my son, Jun Hao' })).toHaveAttribute('href', 'tel:+6580000300')
  expect(screen.getByRole('link', { name: 'Call 1799 anti-scam helpline' })).toHaveAttribute('href', 'tel:1799')
  expect(screen.queryByRole('button', { name: /continue/i })).toBeNull()
  expect(screen.queryByRole('button', { name: /Pause for 24 hours/ })).toBeNull()
  expect(screen.getByRole('group', { name: 'Was this helpful?' })).toBeInTheDocument()
})

test('the verdict is announced in a live region', () => {
  renderVerdict(result('RED'))
  expect(
    screen.getAllByRole('status').some((s) => s.textContent === "On hold. We've paused this transfer to protect you"),
  ).toBe(true)
})

test('AMBER: pause is the primary action; continuing needs the confirm dialog', async () => {
  renderVerdict(result('AMBER'))
  expect(screen.getByText('Pause and check')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Pause for 24 hours' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: 'Call my son, Jun Hao' })).toHaveAttribute('href', 'tel:+6580000300')

  await userEvent.click(screen.getByRole('button', { name: 'I understand the risk, continue' }))
  const dialog = screen.getByRole('dialog', { name: 'Send this payment anyway?' })
  expect(dialog).toHaveTextContent('call your son, Jun Hao or 1799')
  expect(screen.getByRole('button', { name: 'Go back' })).toHaveFocus()

  await userEvent.click(screen.getByRole('button', { name: 'Yes, send S$8,000.00' }))
  expect(await screen.findByText('outcome screen')).toBeInTheDocument()
  expect(choiceCalls()).toEqual([{ choice: 'PROCEEDED', confirmed: true }])
})

test('AMBER: "Pause for 24 hours" records COOL_OFF', async () => {
  renderVerdict(result('AMBER'))
  await userEvent.click(screen.getByRole('button', { name: 'Pause for 24 hours' }))
  expect(await screen.findByText('outcome screen')).toBeInTheDocument()
  expect(choiceCalls()).toEqual([{ choice: 'COOL_OFF', confirmed: false }])
})

test('AMBER needing review says a person will look at it', () => {
  renderVerdict(result('AMBER', { needs_review: true, top_flags: [], typology: 'UNKNOWN' }))
  expect(screen.getByText('A member of our team will also look at this payment.')).toBeInTheDocument()
})

test('GREEN: "Looks good", then continues by itself after 2 seconds', async () => {
  vi.useFakeTimers({ shouldAdvanceTime: true })
  renderVerdict(result('GREEN'))
  expect(screen.getByRole('heading', { level: 1, name: 'Looks good' })).toBeInTheDocument()
  expect(screen.getByText('Your transfer is on its way.')).toBeInTheDocument()
  expect(screen.queryByRole('group', { name: 'Was this helpful?' })).toBeNull() // asked on the next screen

  await act(() => vi.advanceTimersByTimeAsync(1900))
  expect(screen.queryByText('outcome screen')).toBeNull()
  await act(() => vi.advanceTimersByTimeAsync(300))
  expect(await screen.findByText('outcome screen')).toBeInTheDocument()
  expect(choiceCalls()).toEqual([{ choice: 'PROCEEDED', confirmed: false }])
})

test('the verdict screen follows the language (zh)', async () => {
  await i18n.changeLanguage('zh')
  renderVerdict(result('RED'))
  expect(screen.getByText('已暂停')).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '拨打 1799 反诈骗热线' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: '打电话给儿子俊豪' })).toBeInTheDocument()
})

test('without a result the route goes back home', () => {
  render(
    <MemoryRouter initialEntries={['/app/verdict']}>
      <SessionProvider initial={{ personaId: 'cust_001' }}>
        <Routes>
          <Route path="/app/verdict" element={<Verdict />} />
          <Route path="/app/home" element={<p>home screen</p>} />
        </Routes>
      </SessionProvider>
    </MemoryRouter>,
  )
  expect(screen.getByText('home screen')).toBeInTheDocument()
})
