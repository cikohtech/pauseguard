import { ArrowRight } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { LanguageToggle } from '@/components/LanguageToggle'
import { ShieldMark } from '@/components/ShieldMark'
import { Button } from '@/components/ui/button'
import { PRODUCT_NAME } from '@/lib/product'

// Placeholder landing page (phase 00). The real pitch page is built in phase 07 (UI_SPEC Area 3).
export function Landing() {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex items-center justify-between px-6 py-4">
        <ShieldMark />
        <LanguageToggle />
      </header>
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 px-6">
        <h1 className="text-4xl font-semibold tracking-tight">{t('landing.tagline')}</h1>
        <p className="text-lg text-muted-foreground">
          {t('landing.pitch', { product: PRODUCT_NAME })}
        </p>
        <p className="text-sm text-muted-foreground">{t('landing.status')}</p>
        <div className="flex flex-wrap gap-3">
          <Button asChild size="lg">
            <Link to="/app">
              {t('landing.tryApp')}
              <ArrowRight aria-hidden="true" />
            </Link>
          </Button>
          <Button asChild size="lg" variant="outline">
            <Link to="/console">{t('landing.openConsole')}</Link>
          </Button>
        </div>
      </main>
      <footer className="px-6 py-4 text-center text-xs text-muted-foreground">
        {t('landing.footer')}
      </footer>
    </div>
  )
}
