import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate } from 'react-router-dom'

import { Icon } from '@/components/icons/Icon'
import { CheckInSheet } from '@/customer/components/CheckInSheet'
import { AppBar, Screen } from '@/customer/components/Screen'
import type { DemoPersona } from '@/customer/demo'
import { formatSgd, initials } from '@/customer/format'
import { useSession } from '@/customer/session'
import { bigButton } from '@/customer/styles'
import { errorKey } from '@/customer/errors'
import { api } from '@/lib/api'

/** Screen 4: the standard confirm screen. "Send" starts the check (POST /checks). */
export function Review() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const { persona, transfer, check, setCheck, setOutcome, recordSent } = useSession()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)
  const errorLine = useRef<HTMLParagraphElement>(null)

  // On a phone the message can sit under the sticky Send button: bring it into view.
  useEffect(() => {
    if (error) errorLine.current?.scrollIntoView?.({ block: 'nearest' })
  }, [error])

  if (!transfer) return <Navigate to="/app/transfer" replace />
  const p = persona as DemoPersona
  const known = p.savedPayees.some((s) => s.account === transfer.account_number)
  const amount = formatSgd(transfer.amount)

  const send = async () => {
    setError(null)
    // A check that is still waiting for its answer is reused (closing the sheet doesn't cancel it).
    if (check && !check.result && check.question) {
      setSheetOpen(true)
      return
    }
    setBusy(true)
    try {
      const res = await api.createCheck(p.customer_id, transfer, 'en')
      if (res.status === 'DONE' && res.verdict === 'GREEN') {
        // Low risk: no check-in, the payment goes straight through.
        setCheck({ id: res.check_id, question: null, fastVerdict: 'GREEN', result: null, evidence: [] })
        api.choice(res.check_id, 'PROCEEDED').catch(() => {})
        recordSent(transfer)
        setOutcome('sent')
        navigate('/app/done')
        return
      }
      setCheck({
        id: res.check_id,
        question: res.question,
        fastVerdict: null,
        result: null,
        evidence: [],
      })
      setSheetOpen(true)
    } catch (err) {
      setError(t(errorKey(err)))
    } finally {
      setBusy(false)
    }
  }

  const row = (label: string, value: string, mono = false) => (
    <div className="flex min-h-14 items-center justify-between gap-4 rounded-xs bg-surface-container-lowest px-4 py-3 first:rounded-t-xl last:rounded-b-xl">
      <dt className="text-body-l text-on-surface-variant">{label}</dt>
      <dd className={`text-right text-body-l break-words ${mono ? 'tabular-nums' : ''}`}>{value}</dd>
    </div>
  )

  return (
    <>
      <Screen
        header={<AppBar title={t('customer.review.title')} back="/app/transfer" />}
        footer={
          <button type="button" onClick={send} disabled={busy} className={bigButton()}>
            {busy ? (
              <Icon name="progress_activity" className="motion-safe:animate-spin" />
            ) : (
              <Icon name="send" />
            )}
            {busy ? t('customer.review.sending') : t('customer.review.send', { amount })}
          </button>
        }
        className="px-4"
      >
        <p className="px-1 pt-1 text-body-l text-on-surface-variant">{t('customer.review.subtitle')}</p>
        <div className="mt-4 flex flex-col items-center rounded-2xl bg-surface-container-low px-5 pt-6 pb-5 text-center">
          <span
            aria-hidden="true"
            className="inline-flex size-14 items-center justify-center rounded-full bg-primary-container text-title-m text-on-primary-container"
          >
            {initials(transfer.payee_name.replace(/[^A-Za-z ]/g, '')) || <Icon name="person" />}
          </span>
          <p className="sr-only">{t('customer.review.amount')}</p>
          <p data-testid="review-amount" className="mt-3 text-display-s tracking-[-0.02em] tabular-nums">
            {amount}
          </p>
          <p className="mt-1 text-body-l text-on-surface-variant">
            {t('customer.review.to')} <span className="font-medium text-on-surface">{transfer.payee_name}</span>
          </p>
          {!known && (
            <p className="mt-3 inline-flex items-center gap-1.5 rounded-sm bg-tertiary-container px-3 py-1.5 text-label-l font-medium text-on-tertiary-container">
              <Icon name="person_add" className="size-[18px]" />
              {t('customer.review.newPayee')}
            </p>
          )}
        </div>
        <dl className="mt-3 flex flex-col gap-0.5">
          {row(t('customer.review.bank'), transfer.bank_name ?? '—')}
          {row(t('customer.review.account'), transfer.account_number, true)}
          {transfer.note && row(t('customer.review.note'), transfer.note)}
          {row(
            t('customer.review.from'),
            `${t('customer.home.account')} ${t('customer.home.accountNo', { suffix: p.accountSuffix })}`,
          )}
          {row(t('customer.review.fee'), t('customer.review.free'))}
        </dl>
        <button type="button" onClick={() => navigate('/app/transfer')} className={`${bigButton('quiet')} mt-2`}>
          <Icon name="edit_note" />
          {t('customer.review.edit')}
        </button>
        {error && (
          <p
            ref={errorLine}
            role="alert"
            className="mb-4 flex items-start gap-3 rounded-xl bg-error-container p-4 text-body-l text-on-error-container"
          >
            <Icon name="error" className="size-5" />
            {error}
          </p>
        )}
      </Screen>
      {check?.question && (
        <CheckInSheet open={sheetOpen} onOpenChange={setSheetOpen} onError={(key) => setError(t(key))} />
      )}
    </>
  )
}
