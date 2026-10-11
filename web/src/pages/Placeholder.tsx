import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { LanguageToggle } from '@/components/LanguageToggle'
import { ShieldMark } from '@/components/ShieldMark'
import { BANK_NAME, PRODUCT_NAME } from '@/lib/product'

type Area = 'console' | 'notFound'

// Stand-in for /console/* (phase 07) and unknown routes.
export function Placeholder({ area }: { area: Area }) {
  const { t } = useTranslation()
  const vars = { product: PRODUCT_NAME, bank: BANK_NAME }
  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex items-center justify-between px-6 py-4">
        <Link to="/" className="rounded-md focus-visible:ring-3 focus-visible:ring-ring/50">
          <ShieldMark />
        </Link>
        <LanguageToggle />
      </header>
      <main className="mx-auto flex max-w-xl flex-1 flex-col justify-center gap-3 px-6">
        <h1 className="text-2xl font-semibold">{t(`${area}.title`, vars)}</h1>
        {area === 'notFound' ? (
          <Link to="/" className="text-primary underline underline-offset-4">
            {t('notFound.home')}
          </Link>
        ) : (
          <p className="text-muted-foreground">{t(`${area}.placeholder`)}</p>
        )}
      </main>
    </div>
  )
}
