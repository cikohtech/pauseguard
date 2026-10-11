// The demo session: which persona is "logged in", the transfer being made and its check.
// Only the persona survives a reload (sessionStorage); a half-finished transfer starts over.
import { createContext, use } from 'react'

import type { DemoPersona } from '@/customer/demo'
import type { EvidenceSource } from '@/customer/evidence'
import type { CheckInQuestion, CheckResult, Transfer, Verdict } from '@/lib/api'

export type Outcome = 'sent' | 'paused' | 'cancelled'

export interface CheckState {
  id: string
  question: CheckInQuestion | null
  fastVerdict: Verdict | null // GREEN at POST /checks: no check-in
  result: CheckResult | null
  evidence: EvidenceSource[]
}

export interface SentTransfer {
  transfer: Transfer
  at: Date
}

export interface Session {
  persona: DemoPersona | null
  choosePersona: (id: string) => void
  transfer: Transfer | null
  setTransfer: (t: Transfer | null) => void
  check: CheckState | null
  setCheck: (c: CheckState | null) => void
  updateCheck: (patch: Partial<CheckState>) => void
  outcome: Outcome | null
  setOutcome: (o: Outcome | null) => void
  sent: SentTransfer[]
  recordSent: (t: Transfer) => void
  /** Clears the transfer and its check (back to the home screen). */
  resetFlow: () => void
}

export const SessionContext = createContext<Session | null>(null)

export function useSession(): Session {
  const ctx = use(SessionContext)
  if (!ctx) throw new Error('useSession outside SessionProvider')
  return ctx
}
