import { Sparkles, UserPlus } from 'lucide-react'
import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { AppBar, Screen } from '@/customer/components/Screen'
import { BANKS, type DemoPersona } from '@/customer/demo'
import { formatSgd } from '@/customer/format'
import { useSession } from '@/customer/session'
import { bigButton } from '@/customer/styles'
import type { Transfer } from '@/lib/api'
import { cn } from '@/lib/utils'

const NEW = 'new'

interface Form {
  payee: string // index of a saved payee, or NEW
  name: string
  bank: string
  account: string
  amount: string
  note: string
}

type Errors = Partial<Record<'name' | 'account' | 'amount', string>>

function formFrom(p: DemoPersona, t: Transfer | null): Form {
  if (!t) return { payee: '0', name: '', bank: BANKS[0], account: '', amount: '', note: '' }
  const saved = p.savedPayees.findIndex((s) => s.account === t.account_number)
  return {
    payee: saved >= 0 ? String(saved) : NEW,
    name: t.payee_name,
    bank: t.bank_name ?? BANKS[0],
    account: t.account_number,
    amount: String(t.amount),
    note: t.note ?? '',
  }
}

const field =
  'block min-h-12 w-full rounded-xl border border-input bg-card px-3.5 text-[16px] outline-none transition-[border-color,box-shadow] placeholder:text-muted-foreground/80 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/30 aria-invalid:border-destructive'

/** Screen 3: payee (saved or new), amount, note, and the "Prefill demo scenario" link. */
export function TransferForm() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const id = useId()
  const { persona, transfer, setTransfer, sent } = useSession()
  const p = persona as DemoPersona
  const [form, setForm] = useState<Form>(() => formFrom(p, transfer))
  const [errors, setErrors] = useState<Errors>({})
  const [prefilled, setPrefilled] = useState(false)
  const balance = p.balance - sent.reduce((sum, s) => sum + s.transfer.amount, 0)
  const isNew = form.payee === NEW

  const update = (patch: Partial<Form>) => setForm((f) => ({ ...f, ...patch }))

  const prefill = () => {
    setForm(formFrom(p, p.scenario.transfer))
    setErrors({})
    setPrefilled(true)
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    const amount = Number(form.amount.replace(/[,\s]/g, ''))
    const next: Errors = {}
    if (isNew && !form.name.trim()) next.name = t('customer.transfer.errors.payee')
    if (isNew && !/^[0-9][0-9-]{4,30}$/.test(form.account.trim())) {
      next.account = t('customer.transfer.errors.account')
    }
    if (!Number.isFinite(amount) || amount <= 0) next.amount = t('customer.transfer.errors.amount')
    else if (amount > balance) next.amount = t('customer.transfer.errors.balance')
    setErrors(next)
    if (Object.keys(next).length > 0) {
      document.getElementById(`${id}-${Object.keys(next)[0]}`)?.focus()
      return
    }
    const saved = isNew ? null : p.savedPayees[Number(form.payee)]
    setTransfer({
      payee_name: saved ? saved.name : form.name.trim(),
      account_number: saved ? saved.account : form.account.trim(),
      bank_name: saved ? saved.bank : form.bank,
      dest_type: saved ? saved.dest_type : 'LOCAL_BANK',
      amount: Math.round(amount * 100) / 100,
      currency: 'SGD',
      note: form.note.trim() || null,
    })
    navigate('/app/review')
  }

  const err = (k: keyof Errors) =>
    errors[k] ? (
      <p id={`${id}-${k}-error`} className="mt-1.5 text-sm font-medium text-destructive">
        {errors[k]}
      </p>
    ) : null
  const errProps = (k: keyof Errors) => ({
    id: `${id}-${k}`,
    'aria-invalid': errors[k] ? true : undefined,
    'aria-describedby': errors[k] ? `${id}-${k}-error` : undefined,
  })

  return (
    <Screen
      header={<AppBar title={t('customer.transfer.title')} back="/app/home" />}
      footer={
        <button type="submit" form={`${id}-form`} className={bigButton()}>
          {t('customer.transfer.next')}
        </button>
      }
      className="px-5"
    >
      <form id={`${id}-form`} onSubmit={submit} noValidate className="flex flex-col gap-5 py-5">
        <div className="flex items-center justify-between gap-3 rounded-2xl bg-card p-4 ring-1 ring-border">
          <span className="flex flex-col">
            <span className="text-[13px] text-muted-foreground">{t('customer.transfer.from')}</span>
            <span className="font-semibold">
              {t('customer.home.account')} {t('customer.home.accountNo', { suffix: p.accountSuffix })}
            </span>
          </span>
          <span className="text-right text-[13px] text-muted-foreground tabular-nums">
            {t('customer.transfer.available', { balance: formatSgd(balance) })}
          </span>
        </div>

        <button
          type="button"
          onClick={prefill}
          className="inline-flex min-h-11 w-fit items-center gap-2 self-end rounded-full border border-dashed border-primary/50 px-4 text-sm font-semibold text-primary outline-none hover:bg-primary-soft focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <Sparkles aria-hidden="true" className="size-4" />
          {t('customer.transfer.prefill')}
        </button>
        <p role="status" className={cn('-mt-3 text-right text-sm text-muted-foreground', !prefilled && 'sr-only')}>
          {prefilled ? t('customer.transfer.prefilled') : ''}
        </p>

        <fieldset className="flex min-w-0 flex-col gap-2">
          <legend className="mb-2 text-[15px] font-semibold">{t('customer.transfer.to')}</legend>
          <p className="text-[13px] text-muted-foreground">{t('customer.transfer.saved')}</p>
          {p.savedPayees.map((s, i) => (
            <PayeeOption
              key={s.account}
              name={`${id}-payee`}
              value={String(i)}
              checked={form.payee === String(i)}
              onChange={(v) => update({ payee: v })}
              title={s.name}
              detail={`${s.bank} · ${s.account}`}
              initials={s.name.replace(/[^A-Za-z ]/g, '').split(' ').map((w) => w[0]).slice(0, 2).join('')}
            />
          ))}
          <PayeeOption
            name={`${id}-payee`}
            value={NEW}
            checked={isNew}
            onChange={(v) => update({ payee: v })}
            title={t('customer.transfer.newPayee')}
            icon
          />
        </fieldset>

        {isNew && (
          <div className="flex flex-col gap-4 rounded-2xl bg-muted/60 p-4">
            <div>
              <label htmlFor={`${id}-name`} className="mb-1.5 block text-[15px] font-medium">
                {t('customer.transfer.payeeName')}
              </label>
              <input
                {...errProps('name')}
                className={field}
                autoComplete="off"
                value={form.name}
                onChange={(e) => update({ name: e.target.value })}
              />
              {err('name')}
            </div>
            <div>
              <label htmlFor={`${id}-bank`} className="mb-1.5 block text-[15px] font-medium">
                {t('customer.transfer.bank')}
              </label>
              <select
                id={`${id}-bank`}
                className={field}
                value={form.bank}
                onChange={(e) => update({ bank: e.target.value })}
              >
                {BANKS.map((b) => (
                  <option key={b}>{b}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor={`${id}-account`} className="mb-1.5 block text-[15px] font-medium">
                {t('customer.transfer.account')}
              </label>
              <input
                {...errProps('account')}
                className={cn(field, 'tabular-nums')}
                inputMode="numeric"
                autoComplete="off"
                placeholder={t('customer.transfer.accountHint')}
                value={form.account}
                onChange={(e) => update({ account: e.target.value })}
              />
              {err('account')}
            </div>
          </div>
        )}

        <div>
          <label htmlFor={`${id}-amount`} className="mb-1.5 block text-[15px] font-semibold">
            {t('customer.transfer.amount')}
          </label>
          <div className="relative">
            <span aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-[18px] font-semibold text-muted-foreground">
              S$
            </span>
            <input
              {...errProps('amount')}
              className={cn(field, 'pl-11 text-[20px] font-semibold tabular-nums')}
              inputMode="decimal"
              autoComplete="off"
              placeholder="0.00"
              value={form.amount}
              onChange={(e) => update({ amount: e.target.value })}
            />
          </div>
          {err('amount')}
        </div>

        <div>
          <label htmlFor={`${id}-note`} className="mb-1.5 block text-[15px] font-medium">
            {t('customer.transfer.note')}
          </label>
          <input
            id={`${id}-note`}
            className={field}
            maxLength={140}
            value={form.note}
            onChange={(e) => update({ note: e.target.value })}
          />
        </div>
      </form>
    </Screen>
  )
}

function PayeeOption({
  name,
  value,
  checked,
  onChange,
  title,
  detail,
  initials,
  icon,
}: {
  name: string
  value: string
  checked: boolean
  onChange: (v: string) => void
  title: string
  detail?: string
  initials?: string
  icon?: boolean
}) {
  return (
    <label
      className={cn(
        'flex min-h-14 cursor-pointer items-center gap-3 rounded-xl border bg-card px-3.5 py-2.5 transition-colors has-[:focus-visible]:ring-3 has-[:focus-visible]:ring-ring/50',
        checked ? 'border-primary bg-primary-soft' : 'border-border hover:bg-muted',
      )}
    >
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={() => onChange(value)}
        className="size-5 shrink-0 accent-primary"
      />
      <span
        aria-hidden="true"
        className="inline-flex size-9 shrink-0 items-center justify-center rounded-full bg-muted text-[13px] font-semibold text-muted-foreground"
      >
        {icon ? <UserPlus className="size-4" /> : initials}
      </span>
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-[15px] font-medium">{title}</span>
        {detail && <span className="truncate text-[13px] text-muted-foreground tabular-nums">{detail}</span>}
      </span>
    </label>
  )
}
