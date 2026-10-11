import { AppWindow, Building2, CreditCard, Link2, Phone, ShieldBan } from 'lucide-react'

import type { CaseDetail } from '@/console/api'
import { Section, VerdictBadge } from '@/console/components/bits'
import { analystFlags, entityChips, evidenceSources, type EntityKind } from '@/console/evidence'
import { FLAG_LABEL, dateTime } from '@/console/format'
import { EvidenceCard, type EvidenceCopy } from '@/customer/components/EvidenceCard'
import { cn } from '@/lib/utils'

const COPY: EvidenceCopy = {
  title: 'Evidence with flags',
  hint: 'Numbers link each flag to the spot Gemini found it: a box on the upload or a mark in the pasted text.',
  pasted: 'Text the customer pasted',
  pdf: 'PDF (flags quote it below)',
  imageAlt: (name, count) => `Customer upload ${name}, with ${count} flags marked`,
  boxLabel: (n, title) => `Flag ${n}: ${title}`,
  flagTitle: (code) => FLAG_LABEL[code] ?? code,
}

const ENTITY: Record<EntityKind, { label: string; icon: typeof Phone }> = {
  PHONE: { label: 'Phone', icon: Phone },
  URL: { label: 'Link', icon: Link2 },
  ACCOUNT: { label: 'Account', icon: CreditCard },
  ORG: { label: 'Organisation', icon: Building2 },
  APP: { label: 'App', icon: AppWindow },
}

export function EvidenceTab({ detail }: { detail: CaseDetail }) {
  const flags = analystFlags(detail)
  const sources = evidenceSources(detail)
  const chips = entityChips(detail)
  const ev = detail.evidence
  return (
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0">
        {flags.length > 0 ? (
          <EvidenceCard
            flags={flags}
            message={null}
            sources={sources}
            verdict={detail.case.verdict}
            copy={COPY}
            showSeverity
          />
        ) : (
          <Section title="Evidence with flags">
            <p className="text-sm text-muted-foreground">
              {ev?.evidence_present ? 'No warning signs were found in the evidence.' : 'The customer shared no evidence.'}
            </p>
          </Section>
        )}
      </div>

      <div className="flex min-w-0 flex-col gap-4">
        <Section title="Extracted entities">
          {chips.length > 0 ? (
            <ul className="flex flex-wrap gap-2" aria-label="Extracted entities">
              {chips.map((c) => {
                const { label, icon: Icon } = ENTITY[c.kind]
                return (
                  <li
                    key={`${c.kind}-${c.value}`}
                    className={cn(
                      'inline-flex max-w-full items-center gap-1.5 rounded-lg border px-2 py-1 text-sm',
                      c.onWatchlist ? 'border-verdict-red/40 bg-verdict-red-soft' : 'border-border bg-muted/50',
                    )}
                  >
                    <Icon aria-hidden="true" className="size-3.5 shrink-0 text-muted-foreground" />
                    <span className="sr-only">{label}: </span>
                    <span className="truncate font-mono text-[13px]">{c.value}</span>
                    {c.payee && <span className="text-xs text-muted-foreground">payee</span>}
                    {c.onWatchlist && (
                      <span className="inline-flex items-center gap-0.5 text-xs font-semibold text-verdict-red-ink">
                        <ShieldBan aria-hidden="true" className="size-3.5" />
                        on watchlist
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">None found.</p>
          )}
          <p className="mt-3 text-xs text-muted-foreground">
            “Report as scam” adds the phones, links and accounts to the watchlist (official .gov.sg domains and the
            customer’s own contacts are never added).
          </p>
        </Section>

        {ev && (
          <Section title="What the evidence says">
            <p className="text-sm">{ev.summary}</p>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
              {ev.claimed_sender?.name && (
                <>
                  <dt className="text-muted-foreground">Sender</dt>
                  <dd>{ev.claimed_sender.name}</dd>
                </>
              )}
              {ev.claimed_sender?.claimed_org && (
                <>
                  <dt className="text-muted-foreground">Claims to be</dt>
                  <dd>{ev.claimed_sender.claimed_org}</dd>
                </>
              )}
              {ev.claimed_sender?.channel && (
                <>
                  <dt className="text-muted-foreground">Channel</dt>
                  <dd>{ev.claimed_sender.channel}</dd>
                </>
              )}
              {ev.payment_instruction?.reason_given && (
                <>
                  <dt className="text-muted-foreground">Reason given</dt>
                  <dd>{ev.payment_instruction.reason_given}</dd>
                </>
              )}
            </dl>
          </Section>
        )}

        <Section title="Check-in transcript">
          <ol className="flex flex-col gap-3 text-sm">
            {detail.messages.map((m, i) => (
              <li key={i} className={cn('flex flex-col gap-1', m.role === 'customer' && 'items-end text-right')}>
                <span className="text-xs text-muted-foreground">
                  {m.role === 'assistant' ? 'PauseGuard asked' : 'Customer answered'} · {dateTime(new Date(m.ts))}
                </span>
                <span
                  className={cn(
                    'max-w-[90%] rounded-xl px-3 py-2',
                    m.role === 'assistant' ? 'bg-muted' : 'bg-primary-soft text-secondary-foreground',
                  )}
                >
                  {m.text || <em className="text-muted-foreground">(no text)</em>}
                </span>
                {m.pasted_text && (
                  <details className="w-full text-left">
                    <summary className="cursor-pointer text-xs font-medium text-primary">Pasted text (raw)</summary>
                    <pre className="mt-1 max-h-60 overflow-auto rounded-lg bg-muted p-2 font-mono text-xs whitespace-pre-wrap">
                      {m.pasted_text}
                    </pre>
                  </details>
                )}
              </li>
            ))}
          </ol>
        </Section>

        <p className="flex items-center gap-2 text-xs text-muted-foreground">
          <VerdictBadge verdict={detail.case.verdict} /> Evidence links are signed for 5 minutes; reopen the case to
          refresh them.
        </p>
      </div>
    </div>
  )
}
