import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { LanguageToggle } from '@/components/LanguageToggle'
import { ShieldMark } from '@/components/ShieldMark'

// Unknown routes.
export function Placeholder({ area }: { area: 'notFound' }) {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-svh flex-col">
      <header className="flex items-center justify-between px-6 py-4">
        <Link to="/" className="rounded-md focus-visible:ring-3 focus-visible:ring-ring/50">
          <ShieldMark />
        </Link>
        <LanguageToggle />
      </header>
      <main className="mx-auto flex max-w-xl flex-1 flex-col justify-center gap-3 px-6">
        <h1 className="text-2xl font-semibold">{t(`${area}.title`)}</h1>
        <Link to="/" className="text-primary underline underline-offset-4">
          {t('notFound.home')}
        </Link>
      </main>
    </div>
  )
}
