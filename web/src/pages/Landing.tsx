import { ArrowRight, ExternalLink, LayoutDashboard, MessageSquareText, ScanSearch, ShieldCheck, Smartphone } from 'lucide-react'
import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { LanguageToggle } from '@/components/LanguageToggle'
import { ShieldMark } from '@/components/ShieldMark'
import { warmUpApi } from '@/lib/api'
import { PRODUCT_NAME } from '@/lib/product'

const SOURCE_URL =
  'https://www.police.gov.sg/media-hub/police-life/2026/02/scams-and-cybercrime-fell-by-almost-a-quarter-in-2025'

const STEPS = [
  { key: 'check', icon: MessageSquareText },
  { key: 'explain', icon: ScanSearch },
  { key: 'protect', icon: ShieldCheck },
] as const

// The landing page (UI_SPEC Area 3): a one-screen pitch for judges who open the live link.
export function Landing() {
  const { t } = useTranslation()
  const vars = { product: PRODUCT_NAME }
  useEffect(warmUpApi, [])
  return (
    <div className="flex min-h-svh flex-col bg-[linear-gradient(180deg,var(--primary-soft)_0%,var(--background)_55%)]">
      <header className="mx-auto flex w-full max-w-6xl items-center justify-between px-5 py-4 sm:px-8">
        <ShieldMark />
        <LanguageToggle />
      </header>

      <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col justify-center gap-10 px-5 py-6 sm:px-8 lg:gap-14">
        <div className="grid items-center gap-8 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)] lg:gap-14">
          <div className="flex flex-col gap-5">
            <h1 className="text-4xl leading-[1.05] font-semibold tracking-tight text-brand-deep sm:text-6xl">
              {t('landing.tagline')}
            </h1>
            <p className="max-w-xl text-lg text-muted-foreground sm:text-xl">{t('landing.pitch', vars)}</p>
            <div className="mt-2 flex flex-col gap-3 sm:flex-row">
              <Link
                to="/app"
                className="group inline-flex min-h-16 items-center gap-3 rounded-2xl bg-primary px-5 py-3 text-primary-foreground shadow-sm outline-none transition-colors hover:bg-brand-deep focus-visible:ring-4 focus-visible:ring-ring/40"
              >
                <Smartphone aria-hidden="true" className="size-6 shrink-0" />
                <span className="flex flex-col text-left">
                  <span className="text-[17px] font-semibold">{t('landing.tryApp')}</span>
                  <span className="text-sm opacity-90">{t('landing.tryAppHint')}</span>
                </span>
                <ArrowRight aria-hidden="true" className="ml-auto size-5 shrink-0 transition-transform group-hover:translate-x-0.5" />
              </Link>
              <Link
                to="/console"
                className="group inline-flex min-h-16 items-center gap-3 rounded-2xl border border-input bg-card px-5 py-3 shadow-sm outline-none transition-colors hover:border-primary/40 hover:bg-primary-soft focus-visible:ring-4 focus-visible:ring-ring/40"
              >
                <LayoutDashboard aria-hidden="true" className="size-6 shrink-0 text-primary" />
                <span className="flex flex-col text-left">
                  <span className="text-[17px] font-semibold">{t('landing.openConsole')}</span>
                  <span className="text-sm text-muted-foreground">{t('landing.openConsoleHint')}</span>
                </span>
                <ArrowRight aria-hidden="true" className="ml-auto size-5 shrink-0 text-primary transition-transform group-hover:translate-x-0.5" />
              </Link>
            </div>
            <p className="text-sm text-muted-foreground">{t('landing.sideBySide')}</p>
          </div>

          <figure className="rounded-3xl border border-border bg-card p-6 shadow-sm sm:p-8">
            <p className="text-6xl font-semibold tracking-tight text-brand-deep sm:text-7xl">{t('landing.statValue')}</p>
            <blockquote className="mt-3 text-lg leading-snug font-medium">{t('landing.stat')}</blockquote>
            <p className="mt-3 text-[15px] text-muted-foreground">{t('landing.statDetail')}</p>
            <figcaption className="mt-4 border-t border-border pt-3 text-sm">
              <a
                href={SOURCE_URL}
                target="_blank"
                rel="noreferrer noopener"
                className="inline-flex items-center gap-1 rounded text-primary underline underline-offset-4 outline-none hover:text-brand-deep focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                {t('landing.source')}
                <ExternalLink aria-hidden="true" className="size-3.5" />
              </a>
            </figcaption>
          </figure>
        </div>

        <section aria-labelledby="how-title">
          <h2 id="how-title" className="sr-only">
            {t('landing.stepsTitle')}
          </h2>
          <ol className="grid gap-3 sm:grid-cols-3 sm:gap-4">
            {STEPS.map(({ key, icon: Icon }, i) => (
              <li key={key} className="flex gap-4 rounded-2xl border border-border bg-card/80 p-5">
                <span className="inline-flex size-11 shrink-0 items-center justify-center rounded-xl bg-primary-soft text-primary">
                  <Icon aria-hidden="true" className="size-5" />
                </span>
                <span className="flex flex-col gap-1">
                  <span className="font-semibold">
                    <span className="text-muted-foreground">{i + 1}. </span>
                    {t(`landing.steps.${key}.title`)}
                  </span>
                  <span className="text-[15px] leading-snug text-muted-foreground">{t(`landing.steps.${key}.body`, vars)}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>
      </main>

      <footer className="px-5 py-5 text-center text-xs text-muted-foreground sm:px-8">{t('landing.footer')}</footer>
    </div>
  )
}
