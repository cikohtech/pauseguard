import { useTranslation } from 'react-i18next'
import { Link, NavLink } from 'react-router-dom'

import { Icon, type IconName } from '@/components/icons/Icon'
import { PauseGuardLogo } from '@/components/ShieldMark'
import { Avatar } from '@/customer/components/Avatar'
import { HarbourLogo, LangSwitch, Screen } from '@/customer/components/Screen'
import type { DemoPersona, TxnKind } from '@/customer/demo'
import { daysAgo, formatSgd, formatShortDate, sgHour } from '@/customer/format'
import { useSession } from '@/customer/session'
import { PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

const KIND_ICON: Record<TxnKind, IconName> = {
  bill: 'receipt_long',
  paynow: 'mobile',
  income: 'payments',
  rent: 'home_work',
  shopping: 'shopping_bag',
  transfer: 'swap_horiz',
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
      header={
        <header className="pt-sat shrink-0 bg-surface transition-colors duration-200 group-data-[scrolled=true]/screen:bg-surface-container">
          <div className="flex h-16 items-center justify-between gap-1 pr-2 pl-5">
            <HarbourLogo />
            <span className="flex items-center gap-1">
              <LangSwitch />
              <Avatar id={p.customer_id} name={p.full_name} size="sm" className="ml-1 size-9 text-[14px]" />
            </span>
          </div>
        </header>
      }
      navBar={<BottomNav />}
      className="px-4"
    >
      <h1 className="px-1 pt-2 text-headline-s">
        {t(`customer.home.greeting.${greetingKey(sgHour())}`, { name: t(`${key}.short`) })}
      </h1>

      <section className="relative mt-4 overflow-hidden rounded-2xl bg-primary p-5 text-on-primary">
        <Waves />
        <p className="relative flex items-center justify-between text-label-l">
          <span className="inline-flex items-center gap-2">
            <Icon name="savings" className="size-5" />
            {t('customer.home.account')}
          </span>
          <span className="tabular-nums opacity-90">{t('customer.home.accountNo', { suffix: p.accountSuffix })}</span>
        </p>
        <p className="relative mt-6 text-body-m opacity-90">{t('customer.home.available')}</p>
        <p data-testid="balance" className="relative text-display-s font-medium tracking-[-0.02em] tabular-nums">
          {formatSgd(balance)}
        </p>
      </section>

      <Link
        to="/app/transfer"
        className="ripple mt-3 flex min-h-[72px] items-center gap-4 rounded-2xl bg-primary-container p-4 text-on-primary-container"
      >
        <span className="inline-flex size-12 items-center justify-center rounded-xl bg-primary text-on-primary">
          <Icon name="swap_horiz" />
        </span>
        <span className="flex flex-1 flex-col">
          <span className="text-title-m">{t('customer.home.transfer')}</span>
          <span className="text-body-m opacity-85">{t('customer.home.transferHint')}</span>
        </span>
        <Icon name="chevron_right" />
      </Link>

      <p className="mt-3 flex items-center gap-3 rounded-xl bg-secondary-container/70 px-4 py-3 text-body-m text-on-secondary-container">
        <PauseGuardLogo className="size-6" />
        {t('customer.home.protected', { product: PRODUCT_NAME })}
      </p>

      <h2 className="mt-6 mb-2 px-1 text-title-m">{t('customer.home.recent')}</h2>
      <ul className="mb-5 flex flex-col gap-0.5">
        {rows.map((r, i) => (
          <li
            key={i}
            className="flex min-h-[72px] items-center gap-4 rounded-xs bg-surface-container-lowest px-4 py-3 first:rounded-t-xl last:rounded-b-xl"
          >
            <span
              className={cn(
                'inline-flex size-10 shrink-0 items-center justify-center rounded-full',
                r.amount > 0 ? 'bg-verdict-green-soft text-verdict-green-ink' : 'bg-secondary-container text-on-secondary-container',
              )}
            >
              <Icon name={KIND_ICON[r.kind] ?? 'account_balance'} className="size-5" />
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-body-l">{r.title}</span>
              <span className="text-body-m text-on-surface-variant">
                {t(`customer.home.kinds.${r.kind}`)} · {r.when}
              </span>
            </span>
            <span className={cn('text-title-s tabular-nums', r.amount > 0 ? 'text-verdict-green-ink' : 'text-on-surface')}>
              {formatSgd(r.amount, { signed: true })}
            </span>
          </li>
        ))}
      </ul>
    </Screen>
  )
}

/** A quiet harbour-wave pattern on the balance card. */
function Waves() {
  return (
    <svg aria-hidden="true" viewBox="0 0 360 200" preserveAspectRatio="none" className="absolute inset-0 size-full opacity-[0.16]">
      <circle cx="320" cy="20" r="90" fill="currentColor" opacity="0.5" />
      {[120, 145, 170].map((y, i) => (
        <path
          key={y}
          d={`M0 ${y} C 45 ${y - 18}, 90 ${y + 18}, 135 ${y} S 225 ${y - 18}, 270 ${y} S 340 ${y + 14}, 360 ${y}`}
          fill="none"
          stroke="currentColor"
          strokeWidth={6 - i * 1.5}
          strokeLinecap="round"
        />
      ))}
    </svg>
  )
}

/** M3 navigation bar: an active-indicator pill behind the (filled) icon, a label below. */
export function BottomNav() {
  const { t } = useTranslation()
  const items: { to: string; end?: boolean; icon: IconName; label: string }[] = [
    { to: '/app/home', icon: 'home', label: t('customer.nav.home') },
    { to: '/app/transfer', icon: 'swap_horiz', label: t('customer.nav.transfer') },
    { to: '/app', end: true, icon: 'switch_account', label: t('customer.nav.switch') },
  ]
  return (
    <nav aria-label={t('customer.nav.label')} className="shrink-0 bg-surface-container pb-[var(--sab,0px)]">
      <ul className="flex h-20 items-stretch">
        {items.map((it) => (
          <li key={it.to} className="flex flex-1">
            <NavLink to={it.to} end={it.end} className="group/nav flex flex-1 flex-col items-center justify-center gap-1 text-label-m font-medium text-on-surface-variant aria-[current=page]:text-on-surface">
              {({ isActive }) => (
                <>
                  <span
                    className={cn(
                      'ripple inline-flex h-8 w-16 items-center justify-center rounded-full transition-colors duration-200',
                      isActive ? 'bg-secondary-container text-on-secondary-container' : '',
                    )}
                  >
                    <Icon name={it.icon} fill={isActive} />
                  </span>
                  <span className={cn(isActive && 'font-semibold')}>{it.label}</span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  )
}
