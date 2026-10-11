import { ChevronLeft } from 'lucide-react'
import type { ReactNode } from 'react'
import { useTranslation } from 'react-i18next'
import { useNavigate } from 'react-router-dom'

import { cn } from '@/lib/utils'

/** One phone screen: a fixed header, a scrolling body and an optional fixed footer. */
export function Screen({
  header,
  footer,
  children,
  className,
  tone = 'dark',
}: {
  header?: ReactNode
  footer?: ReactNode
  children: ReactNode
  className?: string
  /** 'light' turns the fake status bar white (over a coloured header). */
  tone?: 'light' | 'dark'
}) {
  return (
    <div data-statusbar={tone} className="flex min-h-0 flex-1 flex-col">
      {header}
      <main className={cn('min-h-0 flex-1 overflow-y-auto', className)}>{children}</main>
      {footer && (
        <div className="shrink-0 border-t border-border bg-card px-5 pt-3 pb-safe">{footer}</div>
      )}
    </div>
  )
}

/** The plain white top bar of an inner screen: back, title, language switch. */
export function AppBar({ title, back }: { title: string; back?: string | (() => void) }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  return (
    <header className="pt-sat shrink-0 border-b border-border bg-card">
      <div className="flex h-14 items-center gap-1 px-2">
        {back ? (
          <button
            type="button"
            onClick={() => (typeof back === 'string' ? navigate(back) : back())}
            className="inline-flex size-11 items-center justify-center rounded-full text-foreground outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
            aria-label={t('customer.bar.back')}
          >
            <ChevronLeft aria-hidden="true" className="size-6" />
          </button>
        ) : (
          <span className="w-2" />
        )}
        <h1 className="flex-1 truncate text-[17px] font-semibold">{title}</h1>
        <LangSwitch />
      </div>
    </header>
  )
}

/** The header language toggle (en ⇄ zh), a 44px tap target. */
export function LangSwitch({ onDark = false }: { onDark?: boolean }) {
  const { t, i18n } = useTranslation()
  const next = i18n.language === 'zh' ? 'en' : 'zh'
  return (
    <button
      type="button"
      onClick={() => void i18n.changeLanguage(next)}
      aria-label={`${t('customer.bar.language')}: ${t('customer.bar.switchTo')}`}
      lang={next === 'zh' ? 'zh-Hans' : 'en'}
      className={cn(
        'inline-flex h-11 min-w-11 items-center justify-center rounded-full px-3 text-sm font-semibold outline-none focus-visible:ring-3',
        onDark
          ? 'text-white hover:bg-white/15 focus-visible:ring-white/60'
          : 'text-primary hover:bg-primary-soft focus-visible:ring-ring/50',
      )}
    >
      {t('customer.bar.switchTo')}
    </button>
  )
}

/** Fictional "Harbour Bank" wordmark: a simple wave in a roundel plus the name. */
export function HarbourLogo({ onDark = false }: { onDark?: boolean }) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-2 text-[17px] font-semibold tracking-tight',
        onDark ? 'text-white' : 'text-primary',
      )}
    >
      <svg viewBox="0 0 32 32" aria-hidden="true" className="size-8">
        <circle cx="16" cy="16" r="16" className={onDark ? 'fill-white' : 'fill-primary'} />
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
