import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { Icon, type IconName } from '@/components/icons/Icon'
import { Avatar } from '@/customer/components/Avatar'
import { HarbourLogo, Screen } from '@/customer/components/Screen'
import { PERSONAS, type DemoPersona } from '@/customer/demo'
import { useSession } from '@/customer/session'
import { PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

// What each demo story is about: a scam (the chip is a warning) or a real payment.
const STORY: Record<string, { icon: IconName; scam: boolean }> = {
  cust_001: { icon: 'local_police', scam: true },
  cust_002: { icon: 'mobile_chat', scam: true },
  cust_003: { icon: 'home_work', scam: false },
}

/** Screen 1 (demo only): pick Mrs Tan, Raj or Aisyah; sets customer_id. */
export function PersonaPicker() {
  const { t } = useTranslation()
  const { choosePersona } = useSession()
  const navigate = useNavigate()

  const pick = (p: DemoPersona) => {
    choosePersona(p.customer_id)
    navigate('/app/home')
  }

  return (
    <Screen
      header={
        <header className="pt-sat shrink-0 bg-surface transition-colors group-data-[scrolled=true]/screen:bg-surface-container">
          <div className="flex h-16 items-center pl-5">
            <HarbourLogo />
          </div>
        </header>
      }
      className="px-4 pb-safe"
    >
      <div className="px-1 pt-3">
        <span className="inline-flex items-center gap-1.5 rounded-sm bg-tertiary-container px-2.5 py-1 text-label-m font-medium text-on-tertiary-container">
          <Icon name="verified_user" fill className="size-4" />
          {t('customer.picker.badge', { product: PRODUCT_NAME })}
        </span>
        <h1 className="mt-3 text-headline-m">{t('customer.picker.title')}</h1>
        <p className="mt-1.5 text-body-l text-on-surface-variant">{t('customer.picker.subtitle', { product: PRODUCT_NAME })}</p>
      </div>
      <ul className="stagger mt-6 flex flex-col gap-3">
        {PERSONAS.map((p) => {
          const key = `customer.personas.${p.customer_id}`
          const name = t(`${key}.name`)
          const story = STORY[p.customer_id]
          return (
            <li key={p.customer_id}>
              <button
                type="button"
                onClick={() => pick(p)}
                aria-label={t('customer.picker.choose', { name })}
                aria-describedby={`story-${p.customer_id}`}
                className="ripple flex w-full flex-col gap-3 rounded-xl bg-surface-container-low p-4 text-left text-on-surface transition-shadow duration-200 hover:shadow-e1"
              >
                <span className="flex w-full items-center gap-3.5">
                  <Avatar id={p.customer_id} name={p.full_name} size="lg" />
                  <span className="flex min-w-0 flex-1 flex-col">
                    <span className="text-title-m">{name}</span>
                    <span className="text-body-m text-on-surface-variant">{t('customer.picker.age', { age: p.age })}</span>
                  </span>
                  <span className="inline-flex size-10 items-center justify-center rounded-full bg-surface-container-highest text-on-surface-variant">
                    <Icon name="arrow_forward" className="size-5" />
                  </span>
                </span>
                <span id={`story-${p.customer_id}`} className="text-body-l text-on-surface">
                  {t(`${key}.story`)}
                </span>
                <span
                  className={cn(
                    'inline-flex w-fit items-center gap-1.5 rounded-sm px-2.5 py-1 text-label-l font-medium',
                    story.scam ? 'bg-verdict-red-soft text-verdict-red-ink' : 'bg-verdict-green-soft text-verdict-green-ink',
                  )}
                >
                  <Icon name={story.icon} className="size-[18px]" />
                  {t(`${key}.tag`)}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
      <p className="mt-5 mb-2 flex items-start gap-2 px-1 text-body-s text-on-surface-variant">
        <Icon name="info" className="mt-px size-4" />
        {t('customer.frame.synthetic')}
      </p>
    </Screen>
  )
}
