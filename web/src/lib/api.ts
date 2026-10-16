// Typed client for the PauseGuard API (docs/API_SPEC.md). The types mirror
// backend/app/models/schemas.py; nulls are explicit in every response.
import { getIdToken } from '@/lib/firebase'
import { API_BASE_URL } from '@/lib/product'

export type Verdict = 'GREEN' | 'AMBER' | 'RED'
export type Action = 'PROCEED' | 'COOL_OFF' | 'HOLD_FOR_REVIEW'
export type Language = 'en' | 'zh' | 'ms' | 'ta'
export type DestType = 'LOCAL_BANK' | 'OVERSEAS' | 'CRYPTO_EXCHANGE' | 'MERCHANT' | 'PAYNOW'
export type CheckStatus = 'SCORING' | 'CHECKIN' | 'ANALYSING' | 'DONE' | 'ERROR'
export type ProgressStage =
  | 'SCORING'
  | 'ANALYSING_EVIDENCE'
  | 'CHECKING_INTEL'
  | 'DECIDING'
  | 'WRITING'
  | 'DONE'
export type CustomerChoice = 'COOL_OFF' | 'CALLED_CONTACT' | 'PROCEEDED' | 'CANCELLED'
export type UploadContentType = 'image/png' | 'image/jpeg' | 'image/webp' | 'application/pdf'
export type Typology =
  | 'GOV_OFFICIAL_IMPERSONATION'
  | 'INVESTMENT'
  | 'JOB_TASK'
  | 'PHISHING'
  | 'ECOMMERCE'
  | 'ROMANCE'
  | 'FAKE_FRIEND'
  | 'BEC_INVOICE'
  | 'NONE'
  | 'UNKNOWN'
export type RedFlagCode =
  | 'AUTHORITY_CLAIM'
  | 'URGENCY'
  | 'SECRECY_REQUEST'
  | 'SAFE_ACCOUNT'
  | 'GUARANTEED_RETURNS'
  | 'UPFRONT_FEE'
  | 'PAY_TO_EARN'
  | 'OFF_PLATFORM_PAYMENT'
  | 'REMOTE_ACCESS_APP'
  | 'SUSPICIOUS_URL'
  | 'NEW_NUMBER_FRIEND'
  | 'CHANGED_BANK_DETAILS'
  | 'CRYPTO_DESTINATION'
  | 'COACHING_TO_LIE'
  | 'THREAT_OR_FEAR'
  | 'TOO_GOOD_TO_BE_TRUE'
  | 'PAYEE_NAME_MISMATCH'
  | 'WATCHLIST_MATCH'

export interface Transfer {
  payee_name: string
  account_number: string
  bank_name: string | null
  dest_type: DestType
  amount: number
  currency: string
  note: string | null
}

export interface RedFlag {
  code: RedFlagCode
  severity: 'LOW' | 'MEDIUM' | 'HIGH'
  quote: string
  evidence_index: number | null
  box_2d: number[] | null // [ymin, xmin, ymax, xmax], 0-1000 on the referenced image
}

export interface CustomerMessage {
  language: Language
  headline: string
  body: string
  flag_explanations: { code: RedFlagCode; text: string }[]
  next_steps: string[]
}

export interface CheckInQuestion {
  text: string
  quick_replies: string[]
}

export interface TxnRisk {
  score: number
  reasons: { code: string; label: string; points: number }[]
}

export interface CreateCheckResponse {
  check_id: string
  status: CheckStatus
  txn_risk: TxnRisk | null
  question: CheckInQuestion | null
  verdict: Verdict | null
  customer_message: CustomerMessage | null
}

export interface CheckResult {
  check_id: string
  status: CheckStatus
  verdict: Verdict | null
  action: Action | null
  needs_review: boolean
  typology: Typology | null
  confidence: number | null
  top_flags: RedFlag[]
  customer_message: CustomerMessage | null
  case_id: string | null
  latency_ms: { verdict?: number | null; total?: number | null }
}

export interface SignUploadResponse {
  upload_url: string
  gcs_uri: string
  expires_in: number
  headers: Record<string, string>
}

export interface Persona {
  customer_id: string
  full_name: string
  age: number
  preferred_language: Language
  trusted_contact_name: string | null
  trusted_contact_phone: string | null
  story: string
}

/** The customer-safe check document from GET /checks/{id} (the fields the app reads). */
export interface CheckRecord {
  check_id: string
  status: CheckStatus
  fusion: {
    verdict: Verdict
    action: Action
    top_flags: RedFlag[]
    needs_review: boolean
  } | null
  evidence: { typology_guess: Typology; typology_confidence: number } | null
  customer_message: CustomerMessage | null
  case_id: string | null
  latency_ms: CheckResult['latency_ms']
}

export interface ProgressEvent {
  type: 'status' | 'partial' | 'done' | 'error'
  stage: ProgressStage | null
  data: Record<string, unknown> | null
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string

  constructor(status: number, code: string, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

export const apiUrl = (path: string) => `${API_BASE_URL}/api/v1${path}`

/** Wakes the API while the judge reads the landing page: Cloud Run scales to zero between visits
 *  and a cold start takes about 8 s (DECISIONS, phase 10 pass B). Fire and forget. */
export function warmUpApi(): void {
  fetch(`${API_BASE_URL}/health`).catch(() => {})
}

/** The ID token to send: the customer app's by default; the console passes its analyst's. */
export type TokenSource = () => Promise<string | null>

export async function request<T>(
  method: 'GET' | 'POST',
  path: string,
  body?: unknown,
  getToken: TokenSource = getIdToken,
): Promise<T> {
  const token = await getToken()
  const headers: Record<string, string> = {}
  if (token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  let res: Response
  try {
    res = await fetch(apiUrl(path), {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch {
    throw new ApiError(0, 'NETWORK', 'The server could not be reached.')
  }
  if (!res.ok) {
    let code = 'INTERNAL'
    let message = `HTTP ${res.status}`
    try {
      const err = (await res.json()) as { error?: { code?: string; message?: string } }
      code = err.error?.code ?? code
      message = err.error?.message ?? message
    } catch {
      // not the error envelope (e.g. a proxy error page)
    }
    throw new ApiError(res.status, code, message)
  }
  return (await res.json()) as T
}

export const api = {
  personas: () => request<Persona[]>('GET', '/personas'),

  createCheck: (customerId: string, transfer: Transfer, language: Language) =>
    request<CreateCheckResponse>('POST', '/checks', {
      customer_id: customerId,
      transfer,
      language,
    }),

  signUpload: (checkId: string, filename: string, contentType: UploadContentType) =>
    request<SignUploadResponse>('POST', '/uploads/sign', {
      check_id: checkId,
      filename,
      content_type: contentType,
    }),

  sendMessage: (
    checkId: string,
    msg: { text?: string; quick_reply?: string; evidence_uris: string[]; pasted_text?: string },
  ) => request<CheckResult>('POST', `/checks/${checkId}/messages`, msg),

  choice: (checkId: string, choice: CustomerChoice, confirmed = false) =>
    request<{ check_id: string; customer_choice: CustomerChoice }>(
      'POST',
      `/checks/${checkId}/choice`,
      { choice, confirmed },
    ),

  getCheck: (checkId: string) => request<CheckRecord>('GET', `/checks/${checkId}`),

  feedback: (checkId: string, helpful: boolean) =>
    request<{ feedback_id: string }>('POST', `/checks/${checkId}/feedback`, { helpful }),
}

/** Sign, then PUT the bytes with exactly the signed headers (GCS in cloud, the API locally). */
export async function uploadEvidence(
  checkId: string,
  file: Blob,
  filename: string,
  contentType: UploadContentType,
): Promise<string> {
  const signed = await api.signUpload(checkId, filename, contentType)
  let res: Response
  try {
    res = await fetch(signed.upload_url, { method: 'PUT', headers: signed.headers, body: file })
  } catch {
    throw new ApiError(0, 'NETWORK', 'The upload could not be sent.')
  }
  if (!res.ok) throw new ApiError(res.status, 'UPLOAD_FAILED', `Upload failed (${res.status})`)
  return signed.gcs_uri
}

/** The POST /messages answer rebuilt from the check document (when that request was lost). */
export function resultFromRecord(rec: CheckRecord): CheckResult | null {
  if (rec.status !== 'DONE' || !rec.fusion) return null
  return {
    check_id: rec.check_id,
    status: rec.status,
    verdict: rec.fusion.verdict,
    action: rec.fusion.action,
    needs_review: rec.fusion.needs_review,
    typology: rec.evidence?.typology_guess ?? null,
    confidence: rec.evidence?.typology_confidence ?? null,
    top_flags: rec.fusion.top_flags,
    customer_message: rec.customer_message,
    case_id: rec.case_id,
    latency_ms: rec.latency_ms,
  }
}

/**
 * Waits for a check's verdict by reading the check document every 700 ms (API_SPEC allows
 * polling instead of SSE). Used when the POST /messages response never arrived: the analysis
 * may still finish on the server. Resolves null if the check is still waiting for an answer.
 */
export async function pollResult(checkId: string, timeoutMs = 45_000): Promise<CheckResult | null> {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    const rec = await api.getCheck(checkId)
    const result = resultFromRecord(rec)
    if (result) return result
    if (rec.status === 'CHECKIN') return null
    await new Promise((r) => setTimeout(r, 700))
  }
  throw new ApiError(0, 'TIMEOUT', 'No verdict yet.')
}

/** SSE progress for a check (API_SPEC "GET /checks/{id}/events"). Returns a close function. */
export async function watchCheckEvents(
  checkId: string,
  onEvent: (ev: ProgressEvent) => void,
  onFail: () => void,
): Promise<() => void> {
  if (typeof EventSource === 'undefined') {
    onFail()
    return () => {}
  }
  const token = await getIdToken()
  const qs = token ? `?access_token=${encodeURIComponent(token)}` : ''
  const source = new EventSource(apiUrl(`/checks/${checkId}/events${qs}`))
  const handle = (e: MessageEvent<string>) => {
    try {
      const ev = JSON.parse(e.data) as ProgressEvent
      onEvent(ev)
      if (ev.type === 'done' || ev.type === 'error') source.close()
    } catch {
      // ignore a malformed event; the POST response is the source of truth
    }
  }
  for (const type of ['status', 'partial', 'done', 'error']) {
    source.addEventListener(type, handle as EventListener)
  }
  source.onerror = () => {
    source.close()
    onFail()
  }
  return () => source.close()
}

export const UPLOAD_TYPES: readonly UploadContentType[] = [
  'image/png',
  'image/jpeg',
  'image/webp',
  'application/pdf',
]
export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024
export const MAX_EVIDENCE_ITEMS = 3
