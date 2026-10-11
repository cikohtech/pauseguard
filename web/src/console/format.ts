// Labels and formatting for the analyst console (English only: it is an internal bank tool).
import type { AnalystAction, CaseStatus, WatchlistType } from '@/console/api'
import type { RedFlagCode, Typology, Verdict } from '@/lib/api'

export const TYPOLOGY_LABEL: Record<Typology, string> = {
  GOV_OFFICIAL_IMPERSONATION: 'Government impersonation',
  INVESTMENT: 'Investment scam',
  JOB_TASK: 'Job / task scam',
  PHISHING: 'Phishing',
  ECOMMERCE: 'E-commerce scam',
  ROMANCE: 'Romance scam',
  FAKE_FRIEND: 'Fake friend',
  BEC_INVOICE: 'Invoice fraud (BEC)',
  NONE: 'No scam pattern',
  UNKNOWN: 'Unknown',
}

export const VERDICT_WORD: Record<Verdict, string> = {
  RED: 'Held',
  AMBER: 'Paused',
  GREEN: 'Proceeded',
}

export const ACTION_LABEL: Record<AnalystAction, string> = {
  RELEASE: 'Release',
  HOLD: 'Hold',
  ESCALATE: 'Escalate',
  REPORT_SCAM: 'Report as scam',
}

export const ACTION_KEY: Record<AnalystAction, string> = {
  RELEASE: 'r',
  HOLD: 'h',
  ESCALATE: 'e',
  REPORT_SCAM: 's',
}

export const STATUS_LABEL: Record<CaseStatus, string> = {
  OPEN: 'Open',
  RELEASED: 'Released',
  HELD: 'Held',
  ESCALATED: 'Escalated',
  REPORTED: 'Reported as scam',
}

/** Past-tense toast text for a decision. */
export const DECIDED_LABEL: Record<AnalystAction, string> = {
  RELEASE: 'Payment released',
  HOLD: 'Payment held',
  ESCALATE: 'Case escalated',
  REPORT_SCAM: 'Reported as scam',
}

export const FLAG_LABEL: Record<RedFlagCode, string> = {
  AUTHORITY_CLAIM: 'Claims authority',
  URGENCY: 'Urgency',
  SECRECY_REQUEST: 'Asks for secrecy',
  SAFE_ACCOUNT: '“Safe account”',
  GUARANTEED_RETURNS: 'Guaranteed returns',
  UPFRONT_FEE: 'Upfront fee',
  PAY_TO_EARN: 'Pay to earn',
  OFF_PLATFORM_PAYMENT: 'Off-platform payment',
  REMOTE_ACCESS_APP: 'Remote-access app',
  SUSPICIOUS_URL: 'Suspicious URL',
  NEW_NUMBER_FRIEND: 'Friend on a new number',
  CHANGED_BANK_DETAILS: 'Changed bank details',
  CRYPTO_DESTINATION: 'Crypto destination',
  COACHING_TO_LIE: 'Coached to lie',
  THREAT_OR_FEAR: 'Threat or fear',
  TOO_GOOD_TO_BE_TRUE: 'Too good to be true',
  PAYEE_NAME_MISMATCH: 'Payee name mismatch',
  WATCHLIST_MATCH: 'Watchlist match',
}

export const WATCHLIST_TYPE_LABEL: Record<WatchlistType, string> = {
  PHONE: 'Phone',
  URL: 'Link',
  DOMAIN: 'Domain',
  ACCOUNT: 'Account',
}

const sgd0 = new Intl.NumberFormat('en-SG', { maximumFractionDigits: 0 })
const sgd2 = new Intl.NumberFormat('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** "S$8,000" for whole amounts, "S$450.50" otherwise. */
export function money(amount: number): string {
  return `S$${Number.isInteger(amount) ? sgd0.format(amount) : sgd2.format(amount)}`
}

/** "S$184.5K", "S$1.2M" for KPI tiles and axes. */
export function compactMoney(amount: number): string {
  if (Math.abs(amount) < 10_000) return money(Math.round(amount))
  return `S$${new Intl.NumberFormat('en-SG', { notation: 'compact', maximumFractionDigits: 1 }).format(amount)}`
}

export const percent = (x: number, digits = 0) => `${(x * 100).toFixed(digits)}%`

export const seconds = (ms: number) => `${(ms / 1000).toFixed(ms < 10_000 ? 1 : 0)} s`

/** "just now", "3 min ago", "2 h ago", "4 Oct" */
export function ago(date: Date, now = new Date()): string {
  const s = Math.max(0, Math.round((now.getTime() - date.getTime()) / 1000))
  if (s < 45) return 'just now'
  const m = Math.round(s / 60)
  if (m < 60) return `${m} min ago`
  const h = Math.round(m / 60)
  if (h < 24) return `${h} h ago`
  return dateShort(date)
}

export function dateShort(date: Date): string {
  return new Intl.DateTimeFormat('en-SG', { day: 'numeric', month: 'short', timeZone: 'Asia/Singapore' }).format(date)
}

export function dateTime(date: Date): string {
  return new Intl.DateTimeFormat('en-SG', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
    timeZone: 'Asia/Singapore',
  }).format(date)
}

export function hourLabel(date: Date): string {
  return new Intl.DateTimeFormat('en-SG', { hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZone: 'Asia/Singapore' }).format(date)
}

/** The file name a customer uploaded, from its stored URI ("gs://…/checks/chk_1/0-chat.png"). */
export function uploadName(uri: string): string {
  const last = uri.split('/').pop() ?? uri
  return last.replace(/^\d+-/, '')
}
