import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate } from 'react-router-dom'

import { Icon, type IconName } from '@/components/icons/Icon'
import { Shape, type ShapeName } from '@/components/m3/Expressive'
import { PauseGuardLogo } from '@/components/ShieldMark'
import { FeedbackThumbs } from '@/customer/components/FeedbackThumbs'
import { HarbourLogo, LangSwitch, Screen } from '@/customer/components/Screen'
import { formatDateTime, formatSgd, transferRef } from '@/customer/format'
import { useSession } from '@/customer/session'
import { bigButton } from '@/customer/styles'
import { api } from '@/lib/api'
import { PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

const LOOK: Record<'sent' | 'paused' | 'cancelled', { icon: IconName; shape: ShapeName; tint: string }> = {
  sent: { icon: 'check_circle', shape: 'sunny', tint: 'text-verdict-green' },
  paused: { icon: 'pause_circle', shape: 'cookie9', tint: 'text-verdict-amber' },
  cancelled: { icon: 'undo', shape: 'cookie4', tint: 'text-secondary' },
}

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

  const look = LOOK[outcome]
  const checked = check && (check.fastVerdict === 'GREEN' || check.result?.verdict === 'GREEN')
  const row = (label: string, value: string, mono = false) => (
    <div className="flex min-h-14 items-center justify-between gap-4 rounded-xs bg-surface-container-lowest px-4 py-3 first:rounded-t-xl last:rounded-b-xl">
      <dt className="text-body-l text-on-surface-variant">{label}</dt>
      <dd className={cn('text-right text-body-l font-medium', mono && 'tabular-nums')}>{value}</dd>
    </div>
  )

  return (
    <Screen
      header={
        <header className="pt-sat shrink-0">
          <div className="flex h-16 items-center justify-between pr-1 pl-5">
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
      className="px-4"
    >
      <div data-testid={`outcome-${outcome}`} key={outcome} className="flex flex-col items-center pt-10 text-center">
        <Shape shape={look.shape} spin className={cn('pop-in flex size-28', look.tint)}>
          <Icon name={look.icon} fill className="size-14 text-white" />
        </Shape>
        <h1 ref={heading} tabIndex={-1} className="rise-in mt-6 text-headline-m outline-none">
          {t(`customer.outcome.${outcome}.title`)}
        </h1>
        <p role="status" className="rise-in mt-2 max-w-xs text-body-l text-on-surface-variant">
          {outcome === 'sent' && t('customer.outcome.sent.body', { amount, payee: transfer.payee_name })}
          {outcome === 'paused' &&
            t('customer.outcome.paused.body', {
              when: formatDateTime(new Date(at.getTime() + 86_400_000), i18n.language),
            })}
          {outcome === 'cancelled' && t('customer.outcome.cancelled.body')}
        </p>
      </div>

      {outcome === 'sent' && (
        <dl className="rise-in mt-8 flex flex-col gap-0.5">
          {row(t('customer.review.amount'), amount, true)}
          {row(t('customer.review.to'), transfer.payee_name)}
          {check && row(t('customer.outcome.sent.ref'), transferRef(check.id) ?? '—', true)}
          {row(t('customer.outcome.sent.when'), formatDateTime(at, i18n.language))}
        </dl>
      )}
      {outcome === 'sent' && checked && (
        <p className="mt-4 flex items-center justify-center gap-2 text-body-m text-on-surface-variant">
          <PauseGuardLogo className="size-5" />
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
