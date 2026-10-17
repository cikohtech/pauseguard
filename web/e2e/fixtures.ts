// A fake PauseGuard API for the browser tests, at the network layer (page.route). Responses follow
// docs/API_SPEC.md; the verdicts are what the real agents return for the three demo scenarios.
import type { Page, Route } from '@playwright/test'

export const API = 'http://api.test/api/v1'

type Verdict = 'GREEN' | 'AMBER' | 'RED'

const QUESTION = {
  text: 'Who asked you to make this payment? Did someone contact you first?',
  quick_replies: [
    'A government officer',
    'A job recruiter',
    'An investment group',
    'A friend or family member',
    'A seller',
    "No one, it's my own payment",
  ],
}

const RESULTS: Record<string, Record<string, unknown>> = {
  cust_001: {
    verdict: 'RED',
    action: 'HOLD_FOR_REVIEW',
    typology: 'GOV_OFFICIAL_IMPERSONATION',
    confidence: 0.99,
    top_flags: [
      { code: 'AUTHORITY_CLAIM', severity: 'HIGH', quote: '我是新加坡金融管理局（MAS）调查组的李伟', evidence_index: 0, box_2d: [205, 50, 285, 760] },
      { code: 'SAFE_ACCOUNT', severity: 'HIGH', quote: '您必须马上把钱转到金管局的安全账户', evidence_index: 0, box_2d: [475, 50, 540, 760] },
      { code: 'SUSPICIOUS_URL', severity: 'HIGH', quote: 'mas-gov-verify.example/case/2231', evidence_index: 0, box_2d: [315, 50, 360, 445] },
      { code: 'URGENCY', severity: 'MEDIUM', quote: '今天下午5点前一定要完成', evidence_index: 0, box_2d: [785, 50, 830, 760] },
    ],
    customer_message: {
      language: 'en',
      headline: 'We have paused this payment to protect you',
      body: 'This is not your fault. Scammers are very convincing. A real government officer will never ask you to move money to a "safe account". This payee has been reported by other customers.',
      flag_explanations: [
        { code: 'AUTHORITY_CLAIM', text: 'They say they are an official. Real officials never ask you to transfer money.' },
        { code: 'SAFE_ACCOUNT', text: 'There is no such thing as a "safe account". Officials never ask you to move your savings.' },
        { code: 'SUSPICIOUS_URL', text: 'This link is not an official website. Do not open it or enter your details.' },
        { code: 'URGENCY', text: "They rush you. Scammers create pressure so you don't stop to check." },
      ],
      next_steps: [],
    },
  },
  cust_002: {
    verdict: 'AMBER',
    action: 'COOL_OFF',
    typology: 'JOB_TASK',
    confidence: 0.98,
    top_flags: [
      { code: 'PAY_TO_EARN', severity: 'HIGH', quote: 'To unlock it, top up S$450 to your task wallet.', evidence_index: 0, box_2d: null },
      { code: 'OFF_PLATFORM_PAYMENT', severity: 'MEDIUM', quote: 'Transfer to our finance colleague: Orchid Trust Bank 556-208417-390, name Ahmad Danial.', evidence_index: 0, box_2d: null },
      { code: 'URGENCY', severity: 'MEDIUM', quote: 'Gold slots are limited today, many members are waiting.', evidence_index: 0, box_2d: null },
    ],
    customer_message: {
      language: 'en',
      headline: 'Please pause: this looks like a scam',
      body: 'This is not your fault. Scammers are very convincing. Real employers will never ask you to pay money to unlock tasks or earn income.',
      flag_explanations: [
        { code: 'PAY_TO_EARN', text: 'Real jobs never ask you to pay money to earn money.' },
        { code: 'OFF_PLATFORM_PAYMENT', text: 'They want you to pay a personal account instead of the normal, protected way.' },
        { code: 'URGENCY', text: "They rush you. Scammers create pressure so you don't stop to check." },
      ],
      next_steps: [],
    },
  },
  cust_003: {
    verdict: 'GREEN',
    action: 'PROCEED',
    typology: 'NONE',
    confidence: 0.95,
    top_flags: [],
    customer_message: { language: 'en', headline: 'Looks good', body: 'Your transfer is on its way.', flag_explanations: [], next_steps: [] },
  },
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({
    status,
    contentType: 'application/json',
    headers: { 'Access-Control-Allow-Origin': '*' },
    body: JSON.stringify(body),
  })

/** The SSE stream a finished check replays (API_SPEC "events"), in one response. */
function sse(checkId: string, done: Record<string, unknown>) {
  const events: [string, string | null, unknown][] = [
    ['status', 'ANALYSING_EVIDENCE', null],
    ['status', 'CHECKING_INTEL', null],
    ['partial', 'ANALYSING_EVIDENCE', {}],
    ['partial', 'CHECKING_INTEL', {}],
    ['status', 'DECIDING', null],
    ['partial', 'DECIDING', {}],
    ['status', 'WRITING', null],
    ['done', 'DONE', { check_id: checkId, ...done }],
  ]
  return events
    .map(([type, stage, data]) => `event: ${type}\ndata: ${JSON.stringify({ type, stage, data })}\n\n`)
    .join('')
}

export interface FakeApi {
  /** Resolve to let POST /messages answer (so a test can look at the analysing screen first). */
  release: () => void
  requests: { method: string; path: string; body: unknown }[]
}

export async function fakeApi(page: Page, { holdAnalysis = false } = {}): Promise<FakeApi> {
  let release = () => {}
  const gate = holdAnalysis ? new Promise<void>((r) => (release = r)) : Promise.resolve()
  const requests: FakeApi['requests'] = []
  const checks = new Map<string, { customer: string }>()
  let n = 0

  await page.route('http://api.test/**', async (route) => {
    const req = route.request()
    const url = new URL(req.url())
    const path = url.pathname.replace('/api/v1', '')
    const method = req.method()
    if (method === 'OPTIONS') {
      return route.fulfill({
        status: 204,
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET,POST,PUT',
          'Access-Control-Allow-Headers': '*',
        },
      })
    }
    const body = req.postData() && req.headers()['content-type']?.includes('json') ? req.postDataJSON() : null
    requests.push({ method, path, body })

    if (method === 'GET' && path === '/personas') return json(route, [])
    if (method === 'POST' && path === '/checks') {
      const id = `chk_E2E${String(++n).padStart(5, '0')}`
      checks.set(id, { customer: body.customer_id })
      return json(route, {
        check_id: id,
        status: 'CHECKIN',
        txn_risk: { score: 60, reasons: [] },
        question: QUESTION,
        verdict: null,
        customer_message: null,
      }, 201)
    }
    if (method === 'POST' && path === '/uploads/sign') {
      return json(route, {
        upload_url: `http://api.test/upload/${body.check_id}/${body.filename}`,
        gcs_uri: `gs://e2e/checks/${body.check_id}/0-${body.filename}`,
        expires_in: 600,
        headers: { 'Content-Type': body.content_type },
      })
    }
    if (method === 'PUT' && path.startsWith('/upload/')) return json(route, {})
    const m = /^\/checks\/(chk_\w+)\/(messages|events|choice|feedback)$/.exec(path)
    if (m) {
      const [, id, what] = m
      const result = { status: 'DONE', needs_review: false, case_id: 'case_E2E', latency_ms: { total: 4800 }, ...RESULTS[checks.get(id)?.customer ?? 'cust_003'] }
      if (what === 'messages') {
        await gate
        return json(route, { check_id: id, ...result })
      }
      if (what === 'events') {
        await gate
        return route.fulfill({
          status: 200,
          headers: { 'Content-Type': 'text/event-stream', 'Access-Control-Allow-Origin': '*' },
          body: sse(id, result),
        })
      }
      if (what === 'choice') return json(route, { check_id: id, customer_choice: body.choice })
      return json(route, { feedback_id: 'fb_e2e' }, 201)
    }
    return json(route, { error: { code: 'NOT_FOUND', message: path } }, 404)
  })
  return { release: () => release(), requests }
}

export const verdictOf = (who: 'tan' | 'raj' | 'aisyah'): Verdict =>
  (({ tan: 'RED', raj: 'AMBER', aisyah: 'GREEN' }) as const)[who]
