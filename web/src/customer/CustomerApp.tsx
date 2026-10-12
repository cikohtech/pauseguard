import { ArrowLeft, CircleCheck, CircleDashed, CircleAlert } from 'lucide-react'
import { useEffect, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, Navigate, Route, Routes } from 'react-router-dom'

import { ShieldMark } from '@/components/ShieldMark'
import { pingApi, useApiStatus } from '@/customer/apiStatus'
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

/** The desktop caption beside the phone: what this is, and who you are playing. */
function Caption() {
  const { t } = useTranslation()
  const { persona } = useSession()
  const status = useApiStatus()
  const StatusIcon = { checking: CircleDashed, ok: CircleCheck, down: CircleAlert }[status]
  return (
    <div className="flex flex-col gap-4">
      <ShieldMark />
      <h2 className="text-2xl leading-tight font-semibold tracking-tight">
        {t('app.title', { bank: BANK_NAME, product: PRODUCT_NAME })}
      </h2>
      <p className="text-[15px] leading-relaxed text-muted-foreground">
        {t('customer.frame.intro', { product: PRODUCT_NAME })}
      </p>
      {persona && (
        <p className="text-[15px]">
          <span className="font-semibold">{t(`customer.personas.${persona.customer_id}.name`)}</span>
          {' · '}
          <Link to="/app" className="font-medium text-primary underline underline-offset-4">
            {t('customer.frame.switchPersona')}
          </Link>
        </p>
      )}
      <p className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
        <StatusIcon
          aria-hidden="true"
          className={status === 'ok' ? 'size-4 text-verdict-green-ink' : 'size-4 motion-safe:animate-pulse'}
        />
        {t(`customer.frame.api.${status === 'ok' && !API_BASE_URL.includes('.run.app') ? 'okLocal' : status}`)}
      </p>
      <p className="text-sm text-muted-foreground">{t('customer.frame.synthetic')}</p>
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-primary underline-offset-4 hover:underline">
        <ArrowLeft aria-hidden="true" className="size-4" />
        {t('customer.frame.about', { product: PRODUCT_NAME })}
      </Link>
    </div>
  )
}
