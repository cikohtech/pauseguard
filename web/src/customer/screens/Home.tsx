import {
  ArrowLeftRight,
  ArrowRight,
  Building2,
  House,
  Receipt,
  ShieldCheck,
  ShoppingBag,
  Smartphone,
  UserRound,
  Wallet,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link, NavLink } from 'react-router-dom'

import { HarbourLogo, LangSwitch, Screen } from '@/customer/components/Screen'
import type { DemoPersona, TxnKind } from '@/customer/demo'
import { daysAgo, formatSgd, formatShortDate, sgHour } from '@/customer/format'
import { useSession } from '@/customer/session'
import { PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

const KIND_ICON: Record<TxnKind, typeof Receipt> = {
  bill: Receipt,
  paynow: Smartphone,
  income: Wallet,
  rent: House,
  shopping: ShoppingBag,
  transfer: ArrowLeftRight,
}

function greetingKey(hour: number) {
  if (hour < 12) return 'morning'
  if (hour < 18) return 'afternoon'
  return 'evening'
}

/** Screen 2: balance card, recent transactions and a big "Transfer" button. */
export function Home() {
  const { t, i18n } = useTranslation()
  const { persona, sent } = useSession()
  const p = persona as DemoPersona
  const key = `customer.personas.${p.customer_id}`
  const balance = p.balance - sent.reduce((sum, s) => sum + s.transfer.amount, 0)

  const rows = [
    ...sent.map((s) => ({
      title: s.transfer.payee_name,
      kind: 'transfer' as TxnKind,
      amount: -s.transfer.amount,
      when: t('customer.home.justNow'),
    })),
    ...p.recent.map((r) => ({
      title: r.name ?? t(`customer.home.txn.${r.labelKey}`),
      kind: r.kind,
      amount: r.amount,
      when: formatShortDate(daysAgo(r.daysAgo), i18n.language),
    })),
  ].slice(0, 6)

  return (
    <Screen
      tone="light"
      header={
        <header className="pt-sat shrink-0 bg-gradient-to-b from-brand-deep to-primary text-white">
          <div className="flex h-14 items-center justify-between px-5">
            <HarbourLogo onDark />
            <LangSwitch onDark />
          </div>
          <div className="px-5 pt-1 pb-6">
            <h1 className="text-[22px] font-semibold">
              {t(`customer.home.greeting.${greetingKey(sgHour())}`, { name: t(`${key}.short`) })}
            </h1>
            <div className="mt-4 rounded-2xl bg-white/10 p-4 ring-1 ring-white/15 backdrop-blur">
              <p className="flex items-center justify-between text-sm text-white/90">
                <span>{t('customer.home.account')}</span>
                <span className="tabular-nums">{t('customer.home.accountNo', { suffix: p.accountSuffix })}</span>
              </p>
              <p className="mt-3 text-sm text-white/90">{t('customer.home.available')}</p>
              <p data-testid="balance" className="text-[32px] leading-tight font-semibold tabular-nums">
                {formatSgd(balance)}
              </p>
            </div>
          </div>
        </header>
      }
      footer={<BottomNav />}
      className="px-5"
    >
      <Link
        to="/app/transfer"
        className="mt-5 flex min-h-16 items-center gap-4 rounded-2xl bg-card p-4 shadow-sm ring-1 ring-border outline-none transition-shadow hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <span className="inline-flex size-12 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <ArrowLeftRight aria-hidden="true" className="size-6" />
        </span>
        <span className="flex flex-1 flex-col">
          <span className="text-[18px] font-semibold">{t('customer.home.transfer')}</span>
          <span className="text-sm text-muted-foreground">{t('customer.home.transferHint')}</span>
        </span>
        <ArrowRight aria-hidden="true" className="size-5 text-muted-foreground" />
      </Link>

      <p className="mt-3 flex items-center gap-1.5 text-[13px] text-muted-foreground">
        <ShieldCheck aria-hidden="true" className="size-4 text-primary" />
        {t('customer.home.protected', { product: PRODUCT_NAME })}
      </p>

      <h2 className="mt-6 mb-1 text-[17px] font-semibold">{t('customer.home.recent')}</h2>
      <ul className="mb-4 divide-y divide-border rounded-2xl bg-card px-4 ring-1 ring-border">
        {rows.map((r, i) => {
          const Icon = KIND_ICON[r.kind] ?? Building2
          return (
            <li key={i} className="flex items-center gap-3 py-3">
              <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
                <Icon aria-hidden="true" className="size-5" />
              </span>
              <span className="flex min-w-0 flex-1 flex-col">
                <span className="truncate text-[15px] font-medium">{r.title}</span>
                <span className="text-[13px] text-muted-foreground">
                  {t(`customer.home.kinds.${r.kind}`)} · {r.when}
                </span>
              </span>
              <span
                className={cn(
                  'text-[15px] font-semibold tabular-nums',
                  r.amount > 0 ? 'text-verdict-green-ink' : 'text-foreground',
                )}
              >
                {formatSgd(r.amount, { signed: true })}
              </span>
            </li>
          )
        })}
      </ul>
    </Screen>
  )
}

export function BottomNav() {
  const { t } = useTranslation()
  const item = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex min-h-12 flex-1 flex-col items-center justify-center gap-0.5 rounded-xl text-[12px] font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
      isActive ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
    )
  return (
    <nav aria-label={t('customer.nav.label')} className="-mt-1 flex gap-1">
      <NavLink to="/app/home" className={item}>
        <House aria-hidden="true" className="size-6" />
        {t('customer.nav.home')}
      </NavLink>
      <NavLink to="/app/transfer" className={item}>
        <ArrowLeftRight aria-hidden="true" className="size-6" />
        {t('customer.nav.transfer')}
      </NavLink>
      <NavLink to="/app" end className={item}>
        <UserRound aria-hidden="true" className="size-6" />
        {t('customer.nav.switch')}
      </NavLink>
    </nav>
  )
}
