import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'

import { AppRoutes } from '@/App'
import i18n from '@/i18n'
import en from '@/locales/en.json'
import zh from '@/locales/zh.json'

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  )
}

// A tiny fake of the API for the customer flow (API_SPEC shapes); records every request.
type Handler = (body: unknown) => unknown
const requests: { method: string; path: string; body: unknown }[] = []
function fakeApi(routes: Record<string, Handler>) {
  requests.length = 0
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      const method = init?.method ?? 'GET'
      const p = new URL(url).pathname.replace('/api/v1', '')
      const body = init?.body ? JSON.parse(init.body as string) : null
      requests.push({ method, path: p, body })
      const key = Object.keys(routes).find((k) => new RegExp(`^${k}$`).test(`${method} ${p}`))
      if (!key) return new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: p } }), { status: 404 })
      return new Response(JSON.stringify(routes[key](body)), { status: 200 })
    }),
  )
}

beforeEach(() => {
  try {
    sessionStorage.clear()
  } catch {
    // ignore
  }
})

afterEach(async () => {
  vi.unstubAllGlobals()
  await i18n.changeLanguage('en')
})

test('landing page shows the tagline and both entry points', () => {
  renderAt('/')
  expect(screen.getByRole('heading', { name: 'Pause before you pay.' })).toBeInTheDocument()
  expect(screen.getByRole('link', { name: /Try the customer app/ })).toHaveAttribute('href', '/app')
  expect(screen.getByRole('link', { name: /analyst console/ })).toHaveAttribute('href', '/console')
})

test.each([
  ['/console/dashboard', 'PauseGuard analyst console'],
  ['/nope', 'Page not found'],
])('route %s renders its area', (path, heading) => {
  renderAt(path)
  expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
})

test('a customer screen without a persona goes to the persona picker', () => {
  fakeApi({ 'GET /personas': () => [] })
  renderAt('/app/home')
  expect(screen.getByRole('heading', { name: 'Choose a demo customer' })).toBeInTheDocument()
  expect(screen.getAllByRole('button', { name: /^Continue as/ })).toHaveLength(3)
})

test('picking Mrs Tan switches the app to Chinese; the header toggle switches it back', async () => {
  fakeApi({ 'GET /personas': () => [] })
  renderAt('/app')
  await userEvent.click(screen.getByRole('button', { name: 'Continue as Mrs Tan Mei Ling' }))
  expect(await screen.findByRole('heading', { name: /陈女士，(早上|下午|晚上)好/ })).toBeInTheDocument()
  expect(screen.getByTestId('balance')).toHaveTextContent('S$42,180.55')

  await userEvent.click(screen.getByRole('button', { name: '语言: English' }))
  expect(await screen.findByRole('heading', { name: /Good (morning|afternoon|evening), Mei Ling/ })).toBeInTheDocument()
})

test('Raj: transfer → check-in → analysis → AMBER, with the right API calls', async () => {
  fakeApi({
    'GET /personas': () => [],
    'POST /checks': () => ({
      check_id: 'chk_RAJ',
      status: 'CHECKIN',
      txn_risk: { score: 55, reasons: [] },
      question: {
        text: 'Who asked you to make this payment? Did someone contact you first?',
        quick_replies: ['A government officer', 'A job recruiter', "No one, it's my own payment"],
      },
      verdict: null,
      customer_message: null,
    }),
    'POST /checks/chk_RAJ/messages': () => ({
      check_id: 'chk_RAJ',
      status: 'DONE',
      verdict: 'AMBER',
      action: 'COOL_OFF',
      needs_review: false,
      typology: 'JOB_TASK',
      confidence: 0.97,
      top_flags: [{ code: 'PAY_TO_EARN', severity: 'HIGH', quote: 'top up S$450', evidence_index: null, box_2d: null }],
      customer_message: {
        language: 'en',
        headline: 'Please pause: this looks like a scam',
        body: 'Real jobs never ask you to pay to earn.',
        flag_explanations: [{ code: 'PAY_TO_EARN', text: 'Real jobs never ask you to pay to earn money.' }],
        next_steps: [],
      },
      case_id: 'case_RAJ',
      latency_ms: { total: 5100 },
    }),
  })
  renderAt('/app')
  await userEvent.click(screen.getByRole('button', { name: 'Continue as Raj Kumar' }))
  expect(screen.getByTestId('balance')).toHaveTextContent('S$2,340.20')
  await userEvent.click(screen.getAllByRole('link', { name: /Transfer/ })[0])

  await userEvent.click(screen.getByRole('button', { name: 'Prefill demo scenario' }))
  expect(screen.getByLabelText('Payee name')).toHaveValue('Ahmad Danial')
  expect(screen.getByLabelText('Account number')).toHaveValue('556-208417-390')
  await userEvent.click(screen.getByRole('button', { name: 'Review transfer' }))

  expect(screen.getByTestId('review-amount')).toHaveTextContent('S$450.00')
  expect(screen.getByText('First transfer to this payee')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Send S$450.00' }))

  const sheet = await screen.findByRole('dialog', { name: 'Quick safety check' })
  expect(within(sheet).getByRole('group', { name: /Who asked you to make this payment/ })).toBeInTheDocument()
  await userEvent.click(within(sheet).getByRole('radio', { name: 'A job recruiter' }))
  await userEvent.type(within(sheet).getByLabelText('Tell us more (optional)'), 'He wants a top-up')
  await userEvent.click(within(sheet).getByRole('button', { name: 'Check now' }))

  expect(await screen.findByText('Reading the message')).toBeInTheDocument()
  expect(await screen.findByRole('heading', { level: 1, name: 'Please pause: this looks like a scam' })).toBeInTheDocument()
  expect(screen.getByText('Real jobs never ask you to pay to earn money.')).toBeInTheDocument()

  const created = requests.find((r) => r.method === 'POST' && r.path === '/checks')!
  expect(created.body).toEqual({
    customer_id: 'cust_002',
    language: 'en',
    transfer: {
      payee_name: 'Ahmad Danial',
      account_number: '556-208417-390',
      bank_name: 'Orchid Trust Bank',
      dest_type: 'LOCAL_BANK',
      amount: 450,
      currency: 'SGD',
      note: null,
    },
  })
  const answer = requests.find((r) => r.path === '/checks/chk_RAJ/messages')!
  expect(answer.body).toEqual({ text: 'He wants a top-up', quick_reply: 'A job recruiter', evidence_uris: [] })
})

test('a saved payee and a normal amount go straight through (GREEN at POST /checks)', async () => {
  fakeApi({
    'GET /personas': () => [],
    'POST /checks': () => ({
      check_id: 'chk_FAST1234',
      status: 'DONE',
      txn_risk: { score: 5, reasons: [] },
      question: null,
      verdict: 'GREEN',
      customer_message: null,
    }),
    'POST /checks/chk_FAST1234/choice': () => ({ check_id: 'chk_FAST1234', customer_choice: 'PROCEEDED' }),
  })
  renderAt('/app')
  await userEvent.click(screen.getByRole('button', { name: 'Continue as Nur Aisyah' }))
  await userEvent.click(screen.getAllByRole('link', { name: /Transfer/ })[0])
  await userEvent.click(screen.getByRole('radio', { name: /Salmah Ismail/ }))
  await userEvent.type(screen.getByLabelText('Amount'), '500')
  await userEvent.click(screen.getByRole('button', { name: 'Review transfer' }))
  await userEvent.click(screen.getByRole('button', { name: 'Send S$500.00' }))

  expect(await screen.findByRole('heading', { name: 'Transfer sent' })).toBeInTheDocument()
  expect(screen.getByText('Checked by PauseGuard')).toBeInTheDocument()
  expect(screen.getByText('HB-FAST1234')).toBeInTheDocument()
  await userEvent.click(screen.getByRole('button', { name: 'Back to home' }))
  expect(screen.getByTestId('balance')).toHaveTextContent('S$18,140.75') // 18,640.75 − 500
})

test('the transfer form validates before review', async () => {
  fakeApi({ 'GET /personas': () => [] })
  renderAt('/app')
  await userEvent.click(screen.getByRole('button', { name: 'Continue as Raj Kumar' }))
  await userEvent.click(screen.getAllByRole('link', { name: /Transfer/ })[0])
  await userEvent.click(screen.getByRole('radio', { name: 'New payee' }))
  await userEvent.type(screen.getByLabelText('Amount'), '99999')
  await userEvent.click(screen.getByRole('button', { name: 'Review transfer' }))
  expect(screen.getByLabelText('Payee name')).toHaveAccessibleDescription("Enter the payee's name.")
  expect(screen.getByLabelText('Payee name')).toHaveFocus()
  expect(screen.getByLabelText('Amount')).toHaveAccessibleDescription("That's more than your available balance.")
})

test('en and zh locale files have the same keys', () => {
  const keys = (o: object, p = ''): string[] =>
    Object.entries(o).flatMap(([k, v]) =>
      typeof v === 'object' ? keys(v, `${p}${k}.`) : [`${p}${k}`],
    )
  expect(keys(zh).sort()).toEqual(keys(en).sort())
})
