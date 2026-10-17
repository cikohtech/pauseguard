import { useId, useState, type FormEvent } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { Icon } from '@/components/icons/Icon'
import { Field } from '@/components/m3/Field'
import { chip, fieldBase } from '@/components/m3/styles'
import { AppBar, Screen } from '@/customer/components/Screen'
import { BANKS, type DemoPersona } from '@/customer/demo'
import { formatSgd, initials } from '@/customer/format'
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

const field = cn(fieldBase, 'h-14')

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

  const errProps = (k: keyof Errors, hint = false) => ({
    id: `${id}-${k}`,
    'aria-invalid': errors[k] ? true : undefined,
    'aria-describedby': errors[k] ? `${id}-${k}-error` : hint ? `${id}-${k}-hint` : undefined,
  })

  return (
    <Screen
      header={<AppBar title={t('customer.transfer.title')} back="/app/home" />}
      footer={
        <button type="submit" form={`${id}-form`} className={bigButton()}>
          {t('customer.transfer.next')}
          <Icon name="arrow_forward" />
        </button>
      }
      className="px-4"
    >
      <form id={`${id}-form`} onSubmit={submit} noValidate className="flex flex-col gap-6 pt-2 pb-6">
        <div className="flex items-center gap-3 rounded-xl bg-surface-container-low p-4">
          <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-primary text-on-primary">
            <Icon name="savings" className="size-5" />
          </span>
          <span className="flex min-w-0 flex-1 flex-col">
            <span className="text-label-m text-on-surface-variant">{t('customer.transfer.from')}</span>
            <span className="truncate text-title-s">
              {t('customer.home.account')} {t('customer.home.accountNo', { suffix: p.accountSuffix })}
            </span>
          </span>
          <span className="text-right text-body-s text-on-surface-variant tabular-nums">
            {t('customer.transfer.available', { balance: formatSgd(balance) })}
          </span>
        </div>

        <div className="-mt-2 flex flex-wrap items-center justify-end gap-2">
          <p role="status" className={cn('text-body-s text-on-surface-variant', !prefilled && 'sr-only')}>
            {prefilled ? t('customer.transfer.prefilled') : ''}
          </p>
          <button
            type="button"
            onClick={prefill}
            className={chip(false, 'min-h-11 rounded-md border-0 bg-tertiary-container px-4 text-on-tertiary-container')}
          >
            <Icon name="wand_stars" />
            {t('customer.transfer.prefill')}
          </button>
        </div>

        <fieldset className="flex min-w-0 flex-col">
          <legend className="mb-1 px-1 text-title-m">{t('customer.transfer.to')}</legend>
          <p className="mb-2 px-1 text-label-l text-on-surface-variant">{t('customer.transfer.saved')}</p>
          <div className="flex flex-col gap-0.5">
            {p.savedPayees.map((s, i) => (
              <PayeeOption
                key={s.account}
                name={`${id}-payee`}
                value={String(i)}
                checked={form.payee === String(i)}
                onChange={(v) => update({ payee: v })}
                title={s.name}
                detail={`${s.bank} · ${s.account}`}
                initials={initials(s.name.replace(/[^A-Za-z ]/g, ''))}
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
          </div>
        </fieldset>

        {isNew && (
          <div className="rise-in flex flex-col gap-5 rounded-xl bg-surface-container-low p-4 pt-5 [--field-bg:var(--surface-container-low)]">
            <Field htmlFor={`${id}-name`} label={t('customer.transfer.payeeName')} error={errors.name} errorId={`${id}-name-error`}>
              <input
                {...errProps('name')}
                className={field}
                placeholder=" "
                autoComplete="off"
                value={form.name}
                onChange={(e) => update({ name: e.target.value })}
              />
            </Field>
            <Field htmlFor={`${id}-bank`} label={t('customer.transfer.bank')} float>
              <select
                id={`${id}-bank`}
                className={cn(field, 'appearance-none pr-12')}
                value={form.bank}
                onChange={(e) => update({ bank: e.target.value })}
              >
                {BANKS.map((b) => (
                  <option key={b}>{b}</option>
                ))}
              </select>
              <Icon name="arrow_drop_down" className="pointer-events-none absolute top-4 right-3 text-on-surface-variant" />
            </Field>
            <Field
              htmlFor={`${id}-account`}
              label={t('customer.transfer.account')}
              error={errors.account}
              errorId={`${id}-account-error`}
              hint={t('customer.transfer.accountHint')}
              hintId={`${id}-account-hint`}
            >
              <input
                {...errProps('account', true)}
                className={cn(field, 'tabular-nums')}
                placeholder=" "
                inputMode="numeric"
                autoComplete="off"
                value={form.account}
                onChange={(e) => update({ account: e.target.value })}
              />
            </Field>
          </div>
        )}

        <div className="flex flex-col items-center rounded-xl bg-surface-container-low px-4 pt-4 pb-5">
          <label htmlFor={`${id}-amount`} className="text-title-s text-on-surface-variant">
            {t('customer.transfer.amount')}
          </label>
          <div
            className={cn(
              'mt-2 flex w-full max-w-[280px] items-baseline justify-center gap-1 border-b-2 pb-1 transition-colors focus-within:border-primary',
              errors.amount ? 'border-error' : 'border-outline-variant',
            )}
          >
            <span aria-hidden="true" className="text-headline-s text-on-surface-variant">
              S$
            </span>
            <input
              {...errProps('amount')}
              className="w-full min-w-0 bg-transparent text-center text-display-m font-normal tracking-[-0.02em] text-on-surface caret-primary tabular-nums placeholder:text-outline-variant focus-visible:outline-none"
              inputMode="decimal"
              autoComplete="off"
              placeholder="0.00"
              value={form.amount}
              onChange={(e) => update({ amount: e.target.value })}
            />
          </div>
          {errors.amount && (
            <p id={`${id}-amount-error`} className="mt-2 text-center text-body-m font-medium text-error">
              {errors.amount}
            </p>
          )}
        </div>

        <Field htmlFor={`${id}-note`} label={t('customer.transfer.note')}>
          <input
            id={`${id}-note`}
            className={field}
            placeholder=" "
            maxLength={140}
            value={form.note}
            onChange={(e) => update({ note: e.target.value })}
          />
        </Field>
      </form>
    </Screen>
  )
}

/** An M3 list item with a trailing radio button (the whole row is the target). */
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
        'ripple flex min-h-16 cursor-pointer items-center gap-4 rounded-xs px-4 py-2.5 transition-colors first:rounded-t-xl last:rounded-b-xl has-[:focus-visible]:outline-3 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-[var(--focus)] has-[:focus-visible]:outline-solid',
        checked ? 'bg-secondary-container text-on-secondary-container' : 'bg-surface-container-lowest text-on-surface',
      )}
    >
      <span
        aria-hidden="true"
        className={cn(
          'inline-flex size-10 shrink-0 items-center justify-center rounded-full text-title-s',
          checked ? 'bg-primary text-on-primary' : 'bg-primary-container text-on-primary-container',
        )}
      >
        {icon ? <Icon name="person_add" className="size-5" /> : initials}
      </span>
      <span className="flex min-w-0 flex-1 flex-col">
        <span className="truncate text-body-l">{title}</span>
        {detail && <span className="truncate text-body-m opacity-80 tabular-nums">{detail}</span>}
      </span>
      <input
        type="radio"
        name={name}
        value={value}
        checked={checked}
        onChange={() => onChange(value)}
        className="size-5 shrink-0 cursor-pointer appearance-none rounded-full border-2 border-on-surface-variant transition-[border-color,background] focus-visible:outline-none checked:border-primary checked:bg-[radial-gradient(circle,var(--primary)_0_4.5px,transparent_5px)]"
      />
    </label>
  )
}
