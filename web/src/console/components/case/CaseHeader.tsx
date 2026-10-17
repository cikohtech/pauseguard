import { Link } from 'react-router-dom'

import type { CaseDetail } from '@/console/api'
import { ConfidenceBar, StatusBadge, TypologyChip, VerdictBadge } from '@/console/components/bits'
import { ACTION_LABEL, TYPOLOGY_LABEL, dateTime, money } from '@/console/format'
import { Icon, Sparkle } from '@/components/icons/Icon'
import { Skeleton } from '@/components/ui/skeleton'

const DEST_LABEL: Record<CaseDetail['transfer']['dest_type'], string> = {
  LOCAL_BANK: 'Local bank',
  OVERSEAS: 'Overseas',
  CRYPTO_EXCHANGE: 'Crypto exchange',
  MERCHANT: 'Merchant',
  PAYNOW: 'PayNow',
}

export function CaseHeader({ detail }: { detail: CaseDetail }) {
  const { case: c, transfer: t, fusion, evidence } = detail
  const file = c.case_file
  return (
    <header className="flex flex-col gap-4 px-4 pt-5 pb-4 sm:px-6">
      <Link
        to="/console"
        className="ripple -ml-3 inline-flex min-h-10 w-fit items-center gap-1.5 rounded-full px-3 text-label-l font-medium text-primary lg:hidden"
      >
        <Icon name="arrow_back" className="size-[18px]" />
        All open cases
      </Link>
      <nav aria-label="Breadcrumb" className="hidden items-center gap-1 text-body-m text-on-surface-variant lg:flex">
        <span>Queue</span>
        <Icon name="chevron_right" className="size-4" />
        <span className="truncate font-mono text-[13px]">{c.case_id}</span>
      </nav>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <VerdictBadge verdict={c.verdict} size="lg" />
            <StatusBadge status={c.status} />
            <span className="inline-flex items-center gap-1 text-body-s text-on-surface-variant">
              <Icon name="schedule" className="size-4" />
              Opened {dateTime(new Date(c.created_at))}
            </span>
          </div>
          <h2 className="mt-3 text-headline-s text-on-surface">
            {file?.title ?? `${TYPOLOGY_LABEL[c.typology]} · ${c.customer_name}`}
          </h2>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-body-m text-on-surface-variant">
            <span className="inline-flex items-center gap-1 font-medium text-on-surface">
              <Icon name="person" className="size-4 text-on-surface-variant" />
              <span>
                {c.customer_name}
                {c.customer_age !== null && <span className="font-normal text-on-surface-variant">, {c.customer_age}</span>}
              </span>
            </span>
            <Icon name="arrow_forward" className="size-4" />
            <span className="text-on-surface">{t.payee_name}</span>
            {t.bank_name && <span>· {t.bank_name}</span>}
            <span>·</span>
            <span className="font-mono text-[13px] tabular-nums">{t.account_number}</span>
            <span>· {DEST_LABEL[t.dest_type]}</span>
          </p>
        </div>
        <div className="text-right">
          <p className="text-label-m text-on-surface-variant">Transfer</p>
          <p className="text-display-s tracking-[-0.02em] text-on-surface tabular-nums">{money(t.amount)}</p>
        </div>
      </div>
      <dl className="flex flex-wrap items-center gap-3">
        <div className="flex h-10 items-center gap-3 rounded-full border border-outline-variant pr-4 pl-1.5">
          <dt className="sr-only">Typology</dt>
          <dd className="flex items-center gap-3">
            <TypologyChip typology={evidence?.typology_guess ?? c.typology} className="rounded-full border-0 bg-surface-container-high" />
            <ConfidenceBar value={evidence?.typology_confidence ?? c.confidence} label="Typology confidence" />
          </dd>
        </div>
        <div className="ai-border flex h-10 min-w-0 items-center gap-2 rounded-full pr-4 pl-3">
          <dt className="flex shrink-0 items-center gap-1.5 text-label-l text-on-surface-variant">
            <Sparkle className="size-[18px]" />
            Recommended:
          </dt>
          <dd className="min-w-0 text-label-l">
            {file ? (
              <span className="font-medium text-on-surface">{ACTION_LABEL[file.recommended_action]}</span>
            ) : (
              <span className="inline-flex items-center gap-2 text-on-surface-variant" role="status">
                <Skeleton className="h-4 w-24" />
                Writing the case file…
              </span>
            )}
          </dd>
        </div>
      </dl>
      {fusion?.needs_review && (
        <p className="flex gap-3 rounded-lg bg-verdict-amber-soft px-4 py-3 text-body-m text-verdict-amber-ink">
          <Icon name="person_search" className="size-5" />
          The automatic analysis didn’t finish in time, so the customer got the safe AMBER answer. Please review the
          evidence yourself.
        </p>
      )}
      {evidence?.injection_attempt_detected && (
        <p className="flex gap-3 rounded-lg bg-verdict-red-soft px-4 py-3 text-body-m text-verdict-red-ink">
          <Icon name="shield_lock" fill className="size-5" />
          The evidence contains text that tries to instruct the AI. It was treated as evidence only and counts as a
          warning sign.
        </p>
      )}
    </header>
  )
}
