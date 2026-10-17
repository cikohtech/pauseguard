import type { CaseDetail } from '@/console/api'
import { Section } from '@/console/components/bits'
import { analystFlags, entityChips, evidenceSources, type EntityKind } from '@/console/evidence'
import { FLAG_LABEL, dateTime } from '@/console/format'
import { EvidenceCard, type EvidenceCopy } from '@/customer/components/EvidenceCard'
import { Icon, type IconName } from '@/components/icons/Icon'
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

const ENTITY: Record<EntityKind, { label: string; icon: IconName }> = {
  PHONE: { label: 'Phone', icon: 'call' },
  URL: { label: 'Link', icon: 'link' },
  ACCOUNT: { label: 'Account', icon: 'credit_card' },
  ORG: { label: 'Organisation', icon: 'apartment' },
  APP: { label: 'App', icon: 'apps' },
}

export function EvidenceTab({ detail }: { detail: CaseDetail }) {
  const flags = analystFlags(detail)
  const sources = evidenceSources(detail)
  const chips = entityChips(detail)
  const ev = detail.evidence
  return (
    <div className="grid gap-4 @4xl:grid-cols-[minmax(0,1fr)_340px]">
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
          <Section title="Evidence with flags" icon="document_search">
            <p className="text-body-m text-on-surface-variant">
              {ev?.evidence_present ? 'No warning signs were found in the evidence.' : 'The customer shared no evidence.'}
            </p>
          </Section>
        )}
      </div>

      <div className="flex min-w-0 flex-col gap-4">
        <Section title="Extracted entities" icon="category">
          {chips.length > 0 ? (
            <ul className="flex flex-wrap gap-2" aria-label="Extracted entities">
              {chips.map((c) => {
                const { label, icon } = ENTITY[c.kind]
                return (
                  <li
                    key={`${c.kind}-${c.value}`}
                    className={cn(
                      'inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-sm border px-2.5 py-1 text-body-m',
                      c.onWatchlist ? 'border-transparent bg-verdict-red-soft text-verdict-red-ink' : 'border-outline-variant text-on-surface',
                    )}
                  >
                    <Icon name={icon} className="size-4" />
                    <span className="sr-only">{label}: </span>
                    <span className="truncate font-mono text-[13px]">{c.value}</span>
                    {c.payee && (
                      <span className="rounded-xs bg-surface-container-high px-1.5 text-label-s font-medium text-on-surface-variant">payee</span>
                    )}
                    {c.onWatchlist && (
                      <span className="inline-flex items-center gap-0.5 text-label-m font-medium">
                        <Icon name="policy" fill className="size-3.5" />
                        on watchlist
                      </span>
                    )}
                  </li>
                )
              })}
            </ul>
          ) : (
            <p className="text-body-m text-on-surface-variant">None found.</p>
          )}
          <p className="mt-3 text-body-s text-on-surface-variant">
            “Report as scam” adds the phones, links and accounts to the watchlist (official .gov.sg domains and the
            customer’s own contacts are never added).
          </p>
        </Section>

        {ev && (
          <Section title="What the evidence says" icon="description">
            <p className="text-body-m">{ev.summary}</p>
            <dl className="mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-body-m">
              {ev.claimed_sender?.name && (
                <>
                  <dt className="text-on-surface-variant">Sender</dt>
                  <dd>{ev.claimed_sender.name}</dd>
                </>
              )}
              {ev.claimed_sender?.claimed_org && (
                <>
                  <dt className="text-on-surface-variant">Claims to be</dt>
                  <dd>{ev.claimed_sender.claimed_org}</dd>
                </>
              )}
              {ev.claimed_sender?.channel && (
                <>
                  <dt className="text-on-surface-variant">Channel</dt>
                  <dd>{ev.claimed_sender.channel}</dd>
                </>
              )}
              {ev.payment_instruction?.reason_given && (
                <>
                  <dt className="text-on-surface-variant">Reason given</dt>
                  <dd>{ev.payment_instruction.reason_given}</dd>
                </>
              )}
            </dl>
          </Section>
        )}

        <Section title="Check-in transcript" icon="forum">
          <ol className="flex flex-col gap-3 text-body-m">
            {detail.messages.map((m, i) => (
              <li key={i} className={cn('flex flex-col gap-1', m.role === 'customer' && 'items-end text-right')}>
                <span className="text-body-s text-on-surface-variant">
                  {m.role === 'assistant' ? 'PauseGuard asked' : 'Customer answered'} · {dateTime(new Date(m.ts))}
                </span>
                <span
                  className={cn(
                    'max-w-[90%] rounded-lg px-4 py-2.5 text-left',
                    m.role === 'assistant' ? 'rounded-tl-xs bg-surface-container' : 'rounded-tr-xs bg-primary-container text-on-primary-container',
                  )}
                >
                  {m.text || <em className="text-on-surface-variant">(no text)</em>}
                </span>
                {m.pasted_text && (
                  <details className="w-full text-left">
                    <summary className="cursor-pointer text-label-l font-medium text-primary">Pasted text (raw)</summary>
                    <pre className="mt-1 max-h-60 overflow-auto rounded-lg bg-surface-container p-3 font-mono text-xs whitespace-pre-wrap">
                      {m.pasted_text}
                    </pre>
                  </details>
                )}
              </li>
            ))}
          </ol>
        </Section>

        <p className="flex items-center gap-2 text-body-s text-on-surface-variant">
          <Icon name="lock" className="size-4" />
          Evidence links are signed for 5 minutes; reopen the case to refresh them.
        </p>
      </div>
    </div>
  )
}
