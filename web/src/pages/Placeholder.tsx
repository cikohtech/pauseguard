import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { Icon } from '@/components/icons/Icon'
import { Shape } from '@/components/m3/Expressive'
import { button } from '@/components/m3/styles'
import { ShieldMark } from '@/components/ShieldMark'

// Unknown routes.
export function Placeholder({ area }: { area: 'notFound' }) {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-svh flex-col bg-surface">
      <header className="flex items-center justify-between px-6 py-4">
        <Link to="/" className="rounded-full">
          <ShieldMark />
        </Link>
      </header>
      <main className="mx-auto flex max-w-xl flex-1 flex-col items-center justify-center gap-4 px-6 text-center">
        <Shape shape="cookie9" spin className="size-24 text-primary-container">
          <Icon name="travel_explore" className="size-10 text-on-primary-container" />
        </Shape>
        <h1 className="mt-2 text-headline-m">{t(`${area}.title`)}</h1>
        <Link to="/" className={button('filled', 'md')}>
          <Icon name="arrow_back" />
          {t('notFound.home')}
        </Link>
      </main>
    </div>
  )
}
