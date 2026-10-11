import { ChevronRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { HarbourLogo, LangSwitch, Screen } from '@/customer/components/Screen'
import { PERSONAS, type DemoPersona } from '@/customer/demo'
import { useSession } from '@/customer/session'
import { PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

const AVATAR: Record<string, string> = {
  cust_001: 'bg-[#E6F1F3] text-[#0F5E6E]',
  cust_002: 'bg-[#EEE9F8] text-[#4B3A8C]',
  cust_003: 'bg-[#FBF0E4] text-[#8A4B12]',
}

/** Screen 1 (demo only): pick Mrs Tan, Raj or Aisyah; sets customer_id and the language. */
export function PersonaPicker() {
  const { t, i18n } = useTranslation()
  const { choosePersona } = useSession()
  const navigate = useNavigate()

  const pick = (p: DemoPersona) => {
    choosePersona(p.customer_id)
    void i18n.changeLanguage(p.language)
    navigate('/app/home')
  }

  return (
    <Screen
      header={
        <header className="pt-sat shrink-0 bg-background">
          <div className="flex h-14 items-center justify-between px-5">
            <HarbourLogo />
            <LangSwitch />
          </div>
        </header>
      }
      className="px-5 pb-safe"
    >
      <h1 className="mt-4 text-[26px] leading-tight font-semibold tracking-tight">
        {t('customer.picker.title')}
      </h1>
      <p className="mt-2 text-[16px] text-muted-foreground">
        {t('customer.picker.subtitle', { product: PRODUCT_NAME })}
      </p>
      <ul className="mt-6 flex flex-col gap-3">
        {PERSONAS.map((p) => {
          const key = `customer.personas.${p.customer_id}`
          const name = t(`${key}.name`)
          return (
            <li key={p.customer_id}>
              <button
                type="button"
                onClick={() => pick(p)}
                aria-label={t('customer.picker.choose', { name })}
                aria-describedby={`story-${p.customer_id}`}
                className="flex w-full items-start gap-3.5 rounded-2xl border border-border bg-card p-4 text-left shadow-sm outline-none transition-[box-shadow,border-color] hover:border-primary/40 hover:shadow-md focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    'inline-flex size-12 shrink-0 items-center justify-center rounded-full text-lg font-semibold',
                    AVATAR[p.customer_id],
                  )}
                >
                  {p.full_name.split(' ').map((w) => w[0]).slice(0, 2).join('')}
                </span>
                <span className="flex min-w-0 flex-1 flex-col gap-1">
                  <span className="text-[17px] font-semibold">{name}</span>
                  <span className="text-sm text-muted-foreground">
                    {t('customer.picker.age', { age: p.age })} ·{' '}
                    {t('customer.picker.language', {
                      language: t(`customer.picker.languages.${p.language}`),
                    })}
                  </span>
                  <span id={`story-${p.customer_id}`} className="text-[15px] leading-snug">
                    {t(`${key}.story`)}
                  </span>
                  <span className="mt-1 inline-flex w-fit rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
                    {t(`${key}.tag`)}
                  </span>
                </span>
                <ChevronRight aria-hidden="true" className="mt-3 size-5 shrink-0 text-muted-foreground" />
              </button>
            </li>
          )
        })}
      </ul>
    </Screen>
  )
}
