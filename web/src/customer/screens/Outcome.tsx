import { CircleCheckBig, Clock, ShieldCheck, Undo2 } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate } from 'react-router-dom'

import { FeedbackThumbs } from '@/customer/components/FeedbackThumbs'
import { HarbourLogo, LangSwitch, Screen } from '@/customer/components/Screen'
import { formatDateTime, formatSgd, transferRef } from '@/customer/format'
import { useSession } from '@/customer/session'
import { bigButton } from '@/customer/styles'
import { api } from '@/lib/api'
import { PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

/** After the verdict: transfer sent, paused for 24 hours, or cancelled. */
export function Outcome() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { transfer, check, outcome, setOutcome, resetFlow } = useSession()
  const heading = useRef<HTMLHeadingElement>(null)
  const [busy, setBusy] = useState(false)
  const [at] = useState(() => new Date())

  useEffect(() => {
    heading.current?.focus()
  }, [outcome])

  if (!transfer || !outcome) return <Navigate to="/app/home" replace />

  const amount = formatSgd(transfer.amount)
  const home = () => {
    resetFlow()
    navigate('/app/home')
  }
  const cancel = async () => {
    setBusy(true)
    if (check) await api.choice(check.id, 'CANCELLED').catch(() => {})
    setBusy(false)
    setOutcome('cancelled')
  }

  const look = {
    sent: { icon: CircleCheckBig, tint: 'bg-verdict-green' },
    paused: { icon: Clock, tint: 'bg-verdict-amber' },
    cancelled: { icon: Undo2, tint: 'bg-muted-foreground' },
  }[outcome]
  const Icon = look.icon
  const checked = check && (check.fastVerdict === 'GREEN' || check.result?.verdict === 'GREEN')

  return (
    <Screen
      header={
        <header className="pt-sat shrink-0">
          <div className="flex h-14 items-center justify-between px-5">
            <HarbourLogo />
            <LangSwitch />
          </div>
        </header>
      }
      footer={
        <div className="flex flex-col gap-2">
          {outcome === 'paused' && (
            <button type="button" disabled={busy} onClick={() => void cancel()} className={bigButton('outline')}>
              {t('customer.outcome.paused.cancel')}
            </button>
          )}
          <button type="button" onClick={home} className={bigButton()}>
            {t('customer.outcome.home')}
          </button>
        </div>
      }
      className="px-5"
    >
      <div data-testid={`outcome-${outcome}`} className="flex flex-col items-center pt-10 text-center">
        <span
          aria-hidden="true"
          className={cn(
            'flex size-20 items-center justify-center rounded-full text-white shadow-lg motion-safe:animate-in motion-safe:zoom-in-75',
            look.tint,
          )}
        >
          <Icon className="size-10" />
        </span>
        <h1 ref={heading} tabIndex={-1} className="mt-5 text-[26px] font-semibold outline-none">
          {t(`customer.outcome.${outcome}.title`)}
        </h1>
        <p role="status" className="mt-2 max-w-xs text-[16px] leading-relaxed text-muted-foreground">
          {outcome === 'sent' && t('customer.outcome.sent.body', { amount, payee: transfer.payee_name })}
          {outcome === 'paused' &&
            t('customer.outcome.paused.body', {
              when: formatDateTime(new Date(at.getTime() + 86_400_000), i18n.language),
            })}
          {outcome === 'cancelled' && t('customer.outcome.cancelled.body')}
        </p>
      </div>

      {outcome === 'sent' && (
        <dl className="mt-8 divide-y divide-border rounded-2xl bg-card px-4 ring-1 ring-border">
          <div className="flex justify-between gap-4 py-3">
            <dt className="text-muted-foreground">{t('customer.review.amount')}</dt>
            <dd className="font-semibold tabular-nums">{amount}</dd>
          </div>
          <div className="flex justify-between gap-4 py-3">
            <dt className="text-muted-foreground">{t('customer.review.to')}</dt>
            <dd className="text-right font-medium">{transfer.payee_name}</dd>
          </div>
          {check && (
            <div className="flex justify-between gap-4 py-3">
              <dt className="text-muted-foreground">{t('customer.outcome.sent.ref')}</dt>
              <dd className="font-medium tabular-nums">{transferRef(check.id)}</dd>
            </div>
          )}
          <div className="flex justify-between gap-4 py-3">
            <dt className="text-muted-foreground">{t('customer.outcome.sent.when')}</dt>
            <dd className="font-medium">{formatDateTime(at, i18n.language)}</dd>
          </div>
        </dl>
      )}
      {outcome === 'sent' && checked && (
        <p className="mt-4 flex items-center justify-center gap-1.5 text-sm text-muted-foreground">
          <ShieldCheck aria-hidden="true" className="size-4 text-primary" />
          {t('customer.outcome.sent.checked', { product: PRODUCT_NAME })}
        </p>
      )}
      {outcome === 'sent' && check?.result?.verdict === 'GREEN' && (
        <div className="mt-2">
          <FeedbackThumbs checkId={check.id} />
        </div>
      )}
    </Screen>
  )
}
