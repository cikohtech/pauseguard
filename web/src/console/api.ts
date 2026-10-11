// The analyst side of the PauseGuard API (docs/API_SPEC.md "Analyst endpoints"). Types mirror
// backend/app/models/schemas.py. Every call sends the console's analyst ID token, never the
// customer app's anonymous one.
import { getAnalystToken } from '@/console/auth'
import {
  request,
  type Action,
  type CustomerChoice,
  type RedFlag,
  type RedFlagCode,
  type Transfer,
  type Typology,
  type Verdict,
} from '@/lib/api'

export type CaseStatus = 'OPEN' | 'RELEASED' | 'HELD' | 'ESCALATED' | 'REPORTED'
export type AnalystAction = 'RELEASE' | 'HOLD' | 'ESCALATE' | 'REPORT_SCAM'
export type WatchlistType = 'PHONE' | 'URL' | 'DOMAIN' | 'ACCOUNT'
export type WatchlistSource = 'SEED' | 'ANALYST_REPORT'
export type MetricsRange = 'today' | '7d'

export interface CaseFile {
  title: string
  summary: string
  timeline: string[]
  evidence_points: { flag: RedFlagCode; quote: string; evidence_index: number | null }[]
  intel_points: string[]
  recommended_action: AnalystAction
  recommended_reason: string
  confidence: number
}

export interface CaseRecord {
  case_id: string
  check_id: string
  customer_id: string
  customer_name: string
  customer_age: number | null
  amount: number
  verdict: Verdict
  typology: Typology
  confidence: number
  case_file: CaseFile | null
  status: CaseStatus
  assigned_to: string | null
  created_at: string
  decided_at: string | null
  decision_note: string | null
}

/** A row in the queue (GET /cases, or a Firestore `cases` document). */
export interface CaseSummary {
  case_id: string
  check_id: string
  customer_name: string
  customer_age: number | null
  amount: number
  verdict: Verdict
  typology: Typology
  confidence: number
  status: CaseStatus
  title: string | null
  created_at: string
}

export interface TxnFeatures {
  is_new_payee: boolean
  amount_vs_median_90d: number | null
  dest_type: Transfer['dest_type']
  transfers_to_new_payees_24h: number
  hour_local: number
  customer_age: number | null
  balance_share: number | null
  watchlist_hit: boolean
}

export interface Entities {
  phones: string[]
  urls: string[]
  accounts: string[]
  orgs: string[]
  apps: string[]
}

export interface EvidenceAnalysis {
  evidence_present: boolean
  summary: string
  claimed_sender: { name: string | null; claimed_org: string | null; channel: string | null } | null
  payment_instruction: { amount: number | null; account: string | null; reason_given: string | null } | null
  entities: Entities
  red_flags: RedFlag[]
  typology_guess: Typology
  typology_confidence: number
  language_detected: string
  injection_attempt_detected: boolean
}

export interface WatchlistMatch {
  type: WatchlistType
  value: string
  source: WatchlistSource
  reported_count: number
}

export interface WebFinding {
  query: string
  finding: string
  sources: string[]
  risk: 'LOW' | 'MEDIUM' | 'HIGH'
  search_entry_point_html: string | null
}

export interface ChatMessage {
  role: 'assistant' | 'customer'
  text: string
  evidence_uris: string[]
  pasted_text: string | null
  ts: string
}

export interface AuditEntry {
  actor: string
  action: AnalystAction | string
  case_id: string
  ts: string
  note: string | null
}

export interface CaseDetail {
  case: CaseRecord
  transfer: Transfer
  txn_risk: {
    score: number
    reasons: { code: string; label: string; points: number }[]
    features: TxnFeatures | null
  } | null
  messages: ChatMessage[]
  evidence: EvidenceAnalysis | null
  evidence_links: { index: number; url: string; content_type: string }[]
  intel: { watchlist_matches: WatchlistMatch[]; web_findings: WebFinding[] } | null
  fusion: {
    verdict: Verdict
    action: Action
    reasons: string[]
    top_flags: RedFlag[]
    needs_review: boolean
  } | null
  customer_choice: CustomerChoice | null
  audit: AuditEntry[]
}

export interface CaseHistory {
  customer_id: string
  as_of: string
  days: { day: string; amount: number; count: number }[]
  median_debit_90d: number | null
  transfer_amount: number
}

export interface DecisionResponse {
  case_id: string
  status: CaseStatus
  watchlist_added: number
}

export interface VerdictBucket {
  start: string
  GREEN: number
  AMBER: number
  RED: number
}

export interface Metrics {
  checks: number
  verdicts: Record<Verdict, number>
  money_protected_sgd: number
  false_positive_rate: number
  latency_ms: { p50: number; p95: number }
  top_typologies: { typology: Typology; count: number }[]
  cost_per_check_usd: number | null
  verdicts_over_time: VerdictBucket[]
  latency_histogram: { from_ms: number; to_ms: number | null; count: number }[]
}

export interface WatchlistEntry {
  type: WatchlistType
  value: string
  source: WatchlistSource
  reported_count: number
  first_seen: string
  last_seen: string
  typologies: Typology[]
}

const get = <T>(path: string) => request<T>('GET', path, undefined, getAnalystToken)

export const consoleApi = {
  openCases: () => get<CaseSummary[]>('/cases?status=OPEN&limit=100'),
  getCase: (caseId: string) => get<CaseDetail>(`/cases/${encodeURIComponent(caseId)}`),
  history: (caseId: string) => get<CaseHistory>(`/cases/${encodeURIComponent(caseId)}/history`),
  decide: (caseId: string, action: AnalystAction, note: string | null) =>
    request<DecisionResponse>(
      'POST',
      `/cases/${encodeURIComponent(caseId)}/decision`,
      { action, note: note || null },
      getAnalystToken,
    ),
  metrics: (range: MetricsRange) => get<Metrics>(`/metrics?range=${range}`),
  watchlist: () => get<WatchlistEntry[]>('/watchlist?limit=500'),
}
