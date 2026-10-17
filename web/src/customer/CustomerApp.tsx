import { useEffect, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, Route, Routes } from 'react-router-dom'

import { Icon } from '@/components/icons/Icon'
import { button } from '@/components/m3/styles'
import { ShieldMark } from '@/components/ShieldMark'
import { pingApi, useApiStatus } from '@/customer/apiStatus'
import { Avatar } from '@/customer/components/Avatar'
import { PhoneFrame } from '@/customer/components/PhoneFrame'
import { Home } from '@/customer/screens/Home'
import { Outcome } from '@/customer/screens/Outcome'
import { PersonaPicker } from '@/customer/screens/PersonaPicker'
import { Review } from '@/customer/screens/Review'
import { TransferForm } from '@/customer/screens/TransferForm'
import { Verdict } from '@/customer/screens/Verdict'
import { useSession } from '@/customer/session'
import { SessionProvider } from '@/customer/SessionProvider'
import { API_BASE_URL, BANK_NAME, PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

/** /app: the Harbour Bank customer mock (UI_SPEC Area 1). */
export function CustomerApp() {
  useEffect(() => pingApi(), [])
  return (
    <SessionProvider>
      <PhoneFrame caption={<Caption />}>
        <Routes>
          <Route index element={<PersonaPicker />} />
          <Route path="home" element={<RequirePersona><Home /></RequirePersona>} />
          <Route path="transfer" element={<RequirePersona><TransferForm /></RequirePersona>} />
          <Route path="review" element={<RequirePersona><Review /></RequirePersona>} />
          <Route path="verdict" element={<RequirePersona><Verdict /></RequirePersona>} />
          <Route path="done" element={<RequirePersona><Outcome /></RequirePersona>} />
          <Route path="*" element={<Navigate to="/app" replace />} />
        </Routes>
      </PhoneFrame>
    </SessionProvider>
  )
}

function RequirePersona({ children }: { children: ReactNode }) {
  const { persona } = useSession()
  return persona ? children : <Navigate to="/app" replace />
}

const TRY_STEPS = ['pick', 'transfer', 'answer', 'console'] as const

/** The desktop caption beside the phone: what this is, who you are playing, and how to demo it. */
function Caption() {
  const { t } = useTranslation()
  const { persona } = useSession()
  const status = useApiStatus()
  return (
    <div className="flex flex-col gap-5">
      <ShieldMark />
      <div>
        <h2 className="text-headline-m text-balance text-on-surface">
          {t('app.title', { bank: BANK_NAME, product: PRODUCT_NAME })}
        </h2>
        <p className="mt-2 text-body-l text-on-surface-variant">{t('customer.frame.intro', { product: PRODUCT_NAME })}</p>
      </div>

      {persona && (
        <div className="flex items-center gap-3 rounded-lg bg-surface-container-lowest p-3 pr-2 shadow-e1">
          <Avatar id={persona.customer_id} name={persona.full_name} size="sm" />
          <p className="flex min-w-0 flex-1 flex-col">
            <span className="text-label-m text-on-surface-variant">{t('customer.frame.playing')}</span>
            <span className="truncate text-title-s">{t(`customer.personas.${persona.customer_id}.name`)}</span>
          </p>
          <Link to="/app" className={button('text', 'sm')}>
            {t('customer.frame.switchPersona')}
          </Link>
        </div>
      )}

      <section aria-labelledby="try-title" className="rounded-lg border border-outline-variant bg-surface-container-lowest/80 p-4 backdrop-blur">
        <h3 id="try-title" className="text-title-s text-on-surface">
          {t('customer.frame.tryTitle')}
        </h3>
        <ol className="mt-3 flex flex-col gap-2.5">
          {TRY_STEPS.map((step, i) => (
            <li key={step} className="flex gap-3 text-body-m text-on-surface-variant">
              <span
                aria-hidden="true"
                className="inline-flex size-6 shrink-0 items-center justify-center rounded-full bg-primary-container text-label-m font-medium text-on-primary-container"
              >
                {i + 1}
              </span>
              <span className="pt-0.5">{t(`customer.frame.try.${step}`)}</span>
            </li>
          ))}
        </ol>
        <a
          href="/console"
          target="_blank"
          rel="noreferrer"
          className={button('tonal', 'sm', 'mt-4 w-full')}
        >
          <Icon name="dashboard" />
          {t('customer.frame.consoleLink')}
          <Icon name="open_in_new" className="!size-4" />
          <span className="sr-only">{t('customer.frame.newTab')}</span>
        </a>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        <p
          role="status"
          className={cn(
            'inline-flex min-h-8 items-center gap-2 rounded-sm border px-3 text-label-l font-medium',
            status === 'ok'
              ? 'border-transparent bg-verdict-green-soft text-verdict-green-ink'
              : status === 'down'
                ? 'border-transparent bg-verdict-amber-soft text-verdict-amber-ink'
                : 'border-outline-variant text-on-surface-variant',
          )}
        >
          <span aria-hidden="true" className="relative flex size-2">
            {status === 'ok' && (
              <span className="absolute inline-flex size-full animate-ping rounded-full bg-verdict-green opacity-60 motion-reduce:hidden" />
            )}
            <span
              className={cn(
                'relative inline-flex size-2 rounded-full',
                status === 'ok' ? 'bg-verdict-green' : status === 'down' ? 'bg-verdict-amber' : 'bg-outline motion-safe:animate-pulse',
              )}
            />
          </span>
          {t(`customer.frame.api.${status === 'ok' && !API_BASE_URL.includes('.run.app') ? 'okLocal' : status}`)}
        </p>
      </div>
      <p className="text-body-s text-on-surface-variant">{t('customer.frame.synthetic')}</p>
      <Link to="/" className={button('text', 'sm', '-ml-3 w-fit')}>
        <Icon name="arrow_back" />
        {t('customer.frame.about', { product: PRODUCT_NAME })}
      </Link>
    </div>
  )
}
