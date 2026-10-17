import { useState, type ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { Icon } from '@/components/icons/Icon'
import { iconButton } from '@/components/m3/styles'
import { cn } from '@/lib/utils'

/**
 * One phone screen: a fixed header, a scrolling body and an optional fixed footer (an action area)
 * or navigation bar. The header tints to surface-container once the body scrolls (M3 top app bar
 * "on scroll" state); the screen enters with the M3 shared-axis motion.
 */
export function Screen({
  header,
  footer,
  navBar,
  children,
  className,
  tone = 'dark',
}: {
  header?: ReactNode
  footer?: ReactNode
  navBar?: ReactNode
  children: ReactNode
  className?: string
  /** 'light' turns the status bar white (over a coloured header). */
  tone?: 'light' | 'dark'
}) {
  const [scrolled, setScrolled] = useState(false)
  return (
    <div data-statusbar={tone} data-scrolled={scrolled} className="group/screen screen-in flex min-h-0 flex-1 flex-col">
      {header}
      <main
        onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 4)}
        className={cn('min-h-0 flex-1 overflow-y-auto overscroll-contain', className)}
      >
        {children}
      </main>
      {footer && (
        <div className="shrink-0 border-t border-outline-variant/60 bg-surface px-5 pt-3 pb-safe">{footer}</div>
      )}
      {navBar}
    </div>
  )
}

/** M3 small top app bar: back and title. */
export function AppBar({ title, back }: { title: string; back?: string | (() => void) }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <header className="pt-sat shrink-0 bg-surface transition-colors duration-200 group-data-[scrolled=true]/screen:bg-surface-container">
      <div className="flex h-16 items-center gap-1 px-1">
        {back ? (
          <button
            type="button"
            onClick={() => (typeof back === 'string' ? navigate(back) : back())}
            className={iconButton('standard', 'text-on-surface')}
            aria-label={t('customer.bar.back')}
          >
            <Icon name="arrow_back" />
          </button>
        ) : (
          <span className="w-3" />
        )}
        <h1 className="flex-1 truncate px-1 pr-4 text-title-l">{title}</h1>
      </div>
    </header>
  )
}

/** Fictional "Harbour Bank" wordmark: a wave and an anchor post in a roundel, plus the name. */
export function HarbourLogo({ onDark = false }: { onDark?: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2.5 text-[18px] font-medium tracking-[-0.01em]',
        onDark ? 'text-white' : 'text-on-surface',
      )}
    >
      <svg viewBox="0 0 32 32" aria-hidden="true" className="size-8">
        <rect width="32" height="32" rx="10" className={onDark ? 'fill-white' : 'fill-primary'} />
        <path
          d="M6 18.5c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2M6 23c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2M16 6.5v8M12.5 10.5h7"
          fill="none"
          strokeWidth="2"
          strokeLinecap="round"
          className={onDark ? 'stroke-primary' : 'stroke-white'}
        />
      </svg>
      Harbour Bank
    </span>
  )
}
