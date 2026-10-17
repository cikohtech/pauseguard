import type { IconName } from '@/components/icons/Icon'
import type { AnalystAction, CaseDetail } from '@/console/api'
import { ACTION_LABEL } from '@/console/format'

export interface AuditItem {
  key: string
  at: Date | null
  who: string
  what: string
  note: string | null
  icon: IconName
}

/** The case's history, oldest first: the check-in, the verdict, then every analyst action. */
export function auditEntries(detail: CaseDetail): AuditItem[] {
  const c = detail.case
  const entries: AuditItem[] = []
  const question = detail.messages.find((m) => m.role === 'assistant')
  const answer = [...detail.messages].reverse().find((m) => m.role === 'customer')
  if (question) {
    entries.push({ key: 'q', at: new Date(question.ts), who: 'PauseGuard', what: 'Asked the customer a check-in question', note: null, icon: 'verified_user' })
  }
  if (answer) {
    const n = answer.evidence_uris.length + (answer.pasted_text ? 1 : 0)
    entries.push({
      key: 'a',
      at: new Date(answer.ts),
      who: 'Customer',
      what: n > 0 ? `Answered and shared ${n} piece${n === 1 ? '' : 's'} of evidence` : 'Answered',
      note: null,
      icon: 'person',
    })
  }
  entries.push({
    key: 'v',
    at: new Date(c.created_at),
    who: 'PauseGuard',
    what: `${c.verdict} verdict; case opened${detail.fusion?.needs_review ? ' for manual review' : ''}`,
    note: null,
    icon: 'gavel',
  })
  for (const [i, a] of detail.audit.entries()) {
    const action = a.action as AnalystAction | 'WATCHLIST_ADD'
    entries.push({
      key: `audit-${i}`,
      at: new Date(a.ts),
      who: a.actor,
      what: action === 'WATCHLIST_ADD' ? 'Added to the watchlist' : (ACTION_LABEL[action as AnalystAction] ?? a.action),
      note: a.note,
      icon: action === 'WATCHLIST_ADD' ? 'policy' : 'shield_person',
    })
  }
  return entries
}
