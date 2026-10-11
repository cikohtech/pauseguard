import { ArrowLeft, Bot, ShieldAlert, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'

import type { CaseDetail } from '@/console/api'
import { ConfidenceBar, StatusBadge, TypologyChip, VerdictBadge } from '@/console/components/bits'
import { ACTION_LABEL, TYPOLOGY_LABEL, dateTime, money } from '@/console/format'
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
    <header className="flex flex-col gap-3 border-b border-border bg-card px-4 py-4 sm:px-6">
      <Link
        to="/console"
        className="-ml-1 inline-flex min-h-11 w-fit items-center gap-1 rounded-lg px-1 text-sm font-medium text-primary outline-none focus-visible:ring-3 focus-visible:ring-ring/50 lg:hidden"
      >
        <ArrowLeft aria-hidden="true" className="size-4" />
        All open cases
      </Link>
      <div className="flex flex-wrap items-center gap-2">
        <VerdictBadge verdict={c.verdict} size="lg" />
        <StatusBadge status={c.status} />
        <span className="text-xs text-muted-foreground">
          {c.case_id} · opened {dateTime(new Date(c.created_at))}
        </span>
      </div>
      <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          <h2 className="text-xl leading-tight font-semibold tracking-tight">
            {file?.title ?? `${TYPOLOGY_LABEL[c.typology]} · ${c.customer_name}`}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{c.customer_name}</span>
            {c.customer_age !== null && `, ${c.customer_age}`} → {t.payee_name}
            {t.bank_name && ` · ${t.bank_name}`} · <span className="tabular-nums">{t.account_number}</span> ·{' '}
            {DEST_LABEL[t.dest_type]}
          </p>
        </div>
        <p className="text-3xl font-semibold tracking-tight">{money(t.amount)}</p>
      </div>
      <dl className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
        <div className="flex flex-wrap items-center gap-2">
          <dt className="sr-only">Typology</dt>
          <dd className="flex items-center gap-2">
            <TypologyChip typology={evidence?.typology_guess ?? c.typology} />
            <ConfidenceBar value={evidence?.typology_confidence ?? c.confidence} label="Typology confidence" />
          </dd>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <dt className="flex shrink-0 items-center gap-1 text-muted-foreground">
            <Sparkles aria-hidden="true" className="size-4 text-primary" />
            Recommended:
          </dt>
          <dd className="min-w-0">
            {file ? (
              <span className="font-semibold">{ACTION_LABEL[file.recommended_action]}</span>
            ) : (
              <span className="inline-flex items-center gap-2 text-muted-foreground" role="status">
                <Skeleton className="h-4 w-24" />
                Writing the case file…
              </span>
            )}
          </dd>
        </div>
      </dl>
      {fusion?.needs_review && (
        <p className="flex gap-2 rounded-lg bg-verdict-amber-soft px-3 py-2 text-sm text-verdict-amber-ink">
          <Bot aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          The automatic analysis didn’t finish in time, so the customer got the safe AMBER answer. Please review the
          evidence yourself.
        </p>
      )}
      {evidence?.injection_attempt_detected && (
        <p className="flex gap-2 rounded-lg bg-verdict-red-soft px-3 py-2 text-sm text-verdict-red-ink">
          <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
          The evidence contains text that tries to instruct the AI. It was treated as evidence only and counts as a
          warning sign.
        </p>
      )}
    </header>
  )
}
