import { Bot, ShieldBan, User, UserRound } from 'lucide-react'

import type { AnalystAction, CaseDetail } from '@/console/api'
import { ACTION_LABEL } from '@/console/format'

export interface AuditItem {
  key: string
  at: Date | null
  who: string
  what: string
  note: string | null
  icon: typeof Bot
}

/** The case's history, oldest first: the check-in, the verdict, then every analyst action. */
export function auditEntries(detail: CaseDetail): AuditItem[] {
  const c = detail.case
  const entries: AuditItem[] = []
  const question = detail.messages.find((m) => m.role === 'assistant')
  const answer = [...detail.messages].reverse().find((m) => m.role === 'customer')
  if (question) {
    entries.push({ key: 'q', at: new Date(question.ts), who: 'PauseGuard', what: 'Asked the customer a check-in question', note: null, icon: Bot })
  }
  if (answer) {
    const n = answer.evidence_uris.length + (answer.pasted_text ? 1 : 0)
    entries.push({
      key: 'a',
      at: new Date(answer.ts),
      who: 'Customer',
      what: n > 0 ? `Answered and shared ${n} piece${n === 1 ? '' : 's'} of evidence` : 'Answered',
      note: null,
      icon: UserRound,
    })
  }
  entries.push({
    key: 'v',
    at: new Date(c.created_at),
    who: 'PauseGuard',
    what: `${c.verdict} verdict; case opened${detail.fusion?.needs_review ? ' for manual review' : ''}`,
    note: null,
    icon: Bot,
  })
  for (const [i, a] of detail.audit.entries()) {
    const action = a.action as AnalystAction | 'WATCHLIST_ADD'
    entries.push({
      key: `audit-${i}`,
      at: new Date(a.ts),
      who: a.actor,
      what: action === 'WATCHLIST_ADD' ? 'Added to the watchlist' : (ACTION_LABEL[action as AnalystAction] ?? a.action),
      note: a.note,
      icon: action === 'WATCHLIST_ADD' ? ShieldBan : User,
    })
  }
  return entries
}
