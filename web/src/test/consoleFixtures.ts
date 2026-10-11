// Console test data in the API's shapes (docs/API_SPEC.md "Analyst endpoints"): Mrs Tan's RED
// case as the real agents describe it, plus a queue, metrics and the watchlist.
import type { CaseDetail, CaseSummary, Metrics, WatchlistEntry } from '@/console/api'

export const TAN_DETAIL: CaseDetail = {
  case: {
    case_id: 'case_tan',
    check_id: 'chk_tan',
    customer_id: 'cust_001',
    customer_name: 'Tan Mei Ling',
    customer_age: 67,
    amount: 8000,
    verdict: 'RED',
    typology: 'GOV_OFFICIAL_IMPERSONATION',
    confidence: 0.99,
    case_file: {
      title: 'MAS officer impersonation, S$8,000 to a new payee',
      summary: 'A caller claiming to be from MAS told Mrs Tan to move her savings to a “safe account”.',
      timeline: ['Customer started a S$8,000.00 transfer to Lee Wei Investigation Acct'],
      evidence_points: [{ flag: 'SAFE_ACCOUNT', quote: 'transfer to the safe account', evidence_index: 0 }],
      intel_points: ['Phone +6580000147 reported 4 times'],
      recommended_action: 'REPORT_SCAM',
      recommended_reason: 'Classic government-impersonation pattern with a watchlisted number.',
      confidence: 0.97,
    },
    status: 'OPEN',
    assigned_to: null,
    created_at: '2026-10-11T06:00:05Z',
    decided_at: null,
    decision_note: null,
  },
  transfer: {
    payee_name: 'Lee Wei Investigation Acct',
    account_number: '123-45678-9',
    bank_name: 'Harbour Bank',
    dest_type: 'LOCAL_BANK',
    amount: 8000,
    currency: 'SGD',
    note: 'case 2231',
  },
  txn_risk: {
    score: 85,
    reasons: [
      { code: 'NEW_PAYEE', label: 'First payment to this account', points: 20 },
      { code: 'AMOUNT_SPIKE', label: '28× the usual payment', points: 30 },
      { code: 'SENIOR_CUSTOMER', label: 'Customer is 60 or older', points: 5 },
      { code: 'WATCHLIST_MATCH', label: 'Payee reported before', points: 40 },
    ],
    features: {
      is_new_payee: true,
      amount_vs_median_90d: 28.4,
      dest_type: 'LOCAL_BANK',
      transfers_to_new_payees_24h: 0,
      hour_local: 14,
      customer_age: 67,
      balance_share: 0.19,
      watchlist_hit: true,
    },
  },
  messages: [
    { role: 'assistant', text: '这笔转账是谁让您付的？', evidence_uris: [], pasted_text: null, ts: '2026-10-11T05:59:50Z' },
    {
      role: 'customer',
      text: '他说他是金管局的官员',
      evidence_uris: ['gs://b/checks/chk_tan/0-chat.png', 'gs://b/checks/chk_tan/1-letter.pdf'],
      pasted_text: 'Officer Lee: transfer to the safe account today',
      ts: '2026-10-11T06:00:00Z',
    },
  ],
  evidence: {
    evidence_present: true,
    summary: 'A chat from someone claiming to be an MAS officer demanding a transfer to a safe account.',
    claimed_sender: { name: 'Lee Wei', claimed_org: 'MAS', channel: 'chat' },
    payment_instruction: { amount: 8000, account: '123-45678-9', reason_given: 'Money-laundering investigation' },
    entities: {
      phones: ['+65 8000 0147'],
      urls: ['https://mas-gov-verify.example/case/2231'],
      accounts: ['123-45678-9'],
      orgs: ['MAS'],
      apps: [],
    },
    red_flags: [
      { code: 'SAFE_ACCOUNT', severity: 'HIGH', quote: 'transfer to the safe account', evidence_index: 0, box_2d: [410, 60, 470, 940] },
      { code: 'AUTHORITY_CLAIM', severity: 'HIGH', quote: 'I am Lee Wei from MAS', evidence_index: 0, box_2d: [200, 60, 260, 940] },
      { code: 'URGENCY', severity: 'MEDIUM', quote: 'today', evidence_index: 2, box_2d: null },
    ],
    typology_guess: 'GOV_OFFICIAL_IMPERSONATION',
    typology_confidence: 0.99,
    language_detected: 'zh',
    injection_attempt_detected: false,
  },
  evidence_links: [{ index: 0, url: 'https://storage.example/chat.png?sig=1', content_type: 'image/png' }],
  intel: {
    watchlist_matches: [
      { type: 'PHONE', value: '+6580000147', source: 'SEED', reported_count: 4 },
      { type: 'DOMAIN', value: 'mas-gov-verify.example', source: 'SEED', reported_count: 2 },
    ],
    web_findings: [
      {
        query: 'mas-gov-verify.example scam',
        finding: 'MAS warns that it never asks the public to transfer money.',
        sources: ['https://vertexaisearch.cloud.google.com/grounding-api-redirect/abc'],
        risk: 'HIGH',
        search_entry_point_html: '<div class="chips">mas scam</div>',
      },
    ],
  },
  fusion: {
    verdict: 'RED',
    action: 'HOLD_FOR_REVIEW',
    reasons: ['Payee phone on the watchlist (hard stop)', 'GOV_OFFICIAL_IMPERSONATION at 0.99'],
    top_flags: [
      { code: 'SAFE_ACCOUNT', severity: 'HIGH', quote: 'transfer to the safe account', evidence_index: 0, box_2d: [410, 60, 470, 940] },
      { code: 'WATCHLIST_MATCH', severity: 'HIGH', quote: '+65 8000 0147', evidence_index: null, box_2d: null },
    ],
    needs_review: false,
  },
  customer_choice: null,
  audit: [
    { actor: 'analyst@harbourbank.example', action: 'HOLD', case_id: 'case_tan', ts: '2026-10-11T06:01:00Z', note: 'Called the customer' },
    { actor: 'analyst@harbourbank.example', action: 'WATCHLIST_ADD', case_id: 'case_tan', ts: '2026-10-11T06:02:00Z', note: 'PHONE +6580000147' },
  ],
}

const summary = (over: Partial<CaseSummary>): CaseSummary => ({
  case_id: 'case_x',
  check_id: 'chk_x',
  customer_name: 'Someone',
  customer_age: null,
  amount: 100,
  verdict: 'AMBER',
  typology: 'UNKNOWN',
  confidence: 0.5,
  status: 'OPEN',
  title: null,
  created_at: '2026-10-11T06:00:00Z',
  ...over,
})

export const QUEUE: CaseSummary[] = [
  summary({
    case_id: 'case_raj',
    customer_name: 'Raj Kumar',
    customer_age: 29,
    amount: 450,
    verdict: 'AMBER',
    typology: 'JOB_TASK',
    created_at: '2026-10-11T06:10:00Z',
  }),
  summary({
    case_id: 'case_tan',
    customer_name: 'Tan Mei Ling',
    customer_age: 67,
    amount: 8000,
    verdict: 'RED',
    typology: 'GOV_OFFICIAL_IMPERSONATION',
    created_at: '2026-10-11T06:00:05Z',
  }),
]

export const NEW_CASE: CaseSummary = summary({
  case_id: 'case_new',
  customer_name: 'Nur Aisyah',
  customer_age: 34,
  amount: 2400,
  verdict: 'RED',
  typology: 'ECOMMERCE',
  created_at: '2026-10-11T06:20:00Z',
})

export const METRICS: Metrics = {
  checks: 3,
  verdicts: { GREEN: 1, AMBER: 1, RED: 1 },
  money_protected_sgd: 8450,
  false_positive_rate: 0,
  latency_ms: { p50: 5200, p95: 8800 },
  top_typologies: [
    { typology: 'GOV_OFFICIAL_IMPERSONATION', count: 1 },
    { typology: 'JOB_TASK', count: 1 },
  ],
  cost_per_check_usd: null,
  verdicts_over_time: [
    { start: '2026-10-11T13:00:00+08:00', GREEN: 1, AMBER: 0, RED: 0 },
    { start: '2026-10-11T14:00:00+08:00', GREEN: 0, AMBER: 1, RED: 1 },
  ],
  latency_histogram: [
    { from_ms: 0, to_ms: 2000, count: 0 },
    { from_ms: 4000, to_ms: 6000, count: 2 },
    { from_ms: 20000, to_ms: null, count: 1 },
  ],
}

export const WATCHLIST: WatchlistEntry[] = [
  {
    type: 'DOMAIN',
    value: 'mas-gov-verify.example',
    source: 'ANALYST_REPORT',
    reported_count: 3,
    first_seen: '2026-10-01T00:00:00Z',
    last_seen: new Date().toISOString(),
    typologies: ['GOV_OFFICIAL_IMPERSONATION'],
  },
  {
    type: 'PHONE',
    value: '+6580000147',
    source: 'SEED',
    reported_count: 4,
    first_seen: '2026-09-01T00:00:00Z',
    last_seen: '2026-10-01T00:00:00Z',
    typologies: [],
  },
]
