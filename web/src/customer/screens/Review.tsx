import { CircleAlert, Info, LoaderCircle } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate } from 'react-router-dom'

import { CheckInSheet } from '@/customer/components/CheckInSheet'
import { AppBar, Screen } from '@/customer/components/Screen'
import type { DemoPersona } from '@/customer/demo'
import { formatSgd } from '@/customer/format'
import { useSession } from '@/customer/session'
import { bigButton } from '@/customer/styles'
import { errorKey } from '@/customer/errors'
import { api, type Language } from '@/lib/api'

/** Screen 4: the standard confirm screen. "Send" starts the check (POST /checks). */
export function Review() {
  const { t, i18n } = useTranslation()
  const navigate = useNavigate()
  const { persona, transfer, check, setCheck, setOutcome, recordSent } = useSession()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sheetOpen, setSheetOpen] = useState(false)

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
      const lang: Language = i18n.language === 'zh' ? 'zh' : 'en'
      const res = await api.createCheck(p.customer_id, transfer, lang)
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
    <div className="flex items-start justify-between gap-4 py-3">
      <dt className="text-[15px] text-muted-foreground">{label}</dt>
      <dd className={`text-right text-[15px] font-medium break-words ${mono ? 'tabular-nums' : ''}`}>{value}</dd>
    </div>
  )

  return (
    <>
      <Screen
        header={<AppBar title={t('customer.review.title')} back="/app/transfer" />}
        footer={
          <button type="button" onClick={send} disabled={busy} className={bigButton()}>
            {busy && <LoaderCircle aria-hidden="true" className="motion-safe:animate-spin" />}
            {busy ? t('customer.review.sending') : t('customer.review.send', { amount })}
          </button>
        }
        className="px-5"
      >
        <p className="pt-5 text-[15px] text-muted-foreground">{t('customer.review.subtitle')}</p>
        <div className="mt-4 rounded-2xl bg-card p-5 text-center ring-1 ring-border">
          <p className="text-sm text-muted-foreground">{t('customer.review.amount')}</p>
          <p data-testid="review-amount" className="mt-1 text-[34px] leading-tight font-semibold tabular-nums">
            {amount}
          </p>
          <p className="mt-1 text-[15px]">
            {t('customer.review.to')} <span className="font-semibold">{transfer.payee_name}</span>
          </p>
          {!known && (
            <p className="mx-auto mt-3 inline-flex items-center gap-1.5 rounded-full bg-muted px-3 py-1 text-[13px] font-medium text-muted-foreground">
              <Info aria-hidden="true" className="size-4" />
              {t('customer.review.newPayee')}
            </p>
          )}
        </div>
        <dl className="mt-4 divide-y divide-border rounded-2xl bg-card px-4 ring-1 ring-border">
          {row(t('customer.review.bank'), transfer.bank_name ?? '—')}
          {row(t('customer.review.account'), transfer.account_number, true)}
          {transfer.note && row(t('customer.review.note'), transfer.note)}
          {row(
            t('customer.review.from'),
            `${t('customer.home.account')} ${t('customer.home.accountNo', { suffix: p.accountSuffix })}`,
          )}
          {row(t('customer.review.fee'), t('customer.review.free'))}
        </dl>
        <button
          type="button"
          onClick={() => navigate('/app/transfer')}
          className={`${bigButton('quiet')} mt-2`}
        >
          {t('customer.review.edit')}
        </button>
        {error && (
          <p role="alert" className="mb-4 flex items-start gap-2 rounded-xl bg-verdict-red-soft p-3 text-[15px] text-verdict-red-ink">
            <CircleAlert aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
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
