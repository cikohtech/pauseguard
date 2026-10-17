import { useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { Link } from 'react-router-dom'

import { Icon, Sparkle, type IconName } from '@/components/icons/Icon'
import { Shape, type ShapeName } from '@/components/m3/Expressive'
import { LanguageToggle } from '@/components/LanguageToggle'
import { ShieldMark } from '@/components/ShieldMark'
import { warmUpApi } from '@/lib/api'
import { PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

const SOURCE_URL =
  'https://www.police.gov.sg/media-hub/police-life/2026/02/scams-and-cybercrime-fell-by-almost-a-quarter-in-2025'

const STEPS: { key: 'check' | 'explain' | 'protect'; icon: IconName; shape: ShapeName; tone: string }[] = [
  { key: 'check', icon: 'forum', shape: 'cookie9', tone: 'text-[#D3E3FD] [&_svg+span]:text-[#041E49]' },
  { key: 'explain', icon: 'document_search', shape: 'sunny', tone: 'text-[#FFE08A] [&_svg+span]:text-[#3D2E00]' },
  { key: 'protect', icon: 'verified_user', shape: 'cookie6', tone: 'text-[#C4EED0] [&_svg+span]:text-[#072711]' },
]

// The contest's named technologies first; each with what it does here.
const STACK: { name: string; icon: IconName | 'gemini' }[] = [
  { name: 'Gemini', icon: 'gemini' },
  { name: 'Agent Development Kit', icon: 'hub' },
  { name: 'Cloud Run', icon: 'deployed_code' },
  { name: 'Firestore', icon: 'database' },
  { name: 'Firebase', icon: 'bolt' },
  { name: 'BigQuery', icon: 'query_stats' },
  { name: 'Vertex AI', icon: 'network_intelligence' },
]

// The landing page (UI_SPEC Area 3): a one-screen pitch for judges who open the live link.
export function Landing() {
  const { t } = useTranslation()
  const vars = { product: PRODUCT_NAME }
  useEffect(warmUpApi, [])
  return (
    <div className="relative flex min-h-svh flex-col overflow-hidden bg-surface">
      <Backdrop />
      <header className="relative mx-auto flex w-full max-w-7xl items-center justify-between px-5 py-4 sm:px-8">
        <ShieldMark />
        <LanguageToggle />
      </header>

      <main className="relative mx-auto flex w-full max-w-7xl flex-1 flex-col gap-16 px-5 pt-6 pb-12 sm:px-8 lg:pt-12">
        <div className="grid items-center gap-12 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)]">
          <div className="rise-in flex flex-col gap-6">
            <p className="inline-flex w-fit items-center gap-2 rounded-full border border-outline-variant bg-surface-container-lowest py-1.5 pr-4 pl-3 text-label-l text-on-surface-variant">
              <Sparkle className="size-4" />
              {t('landing.eyebrow')}
            </p>
            <h1 className="bg-gradient-to-r from-[#0B57D0] via-[#3B5FD9] to-[#7B3FD1] bg-clip-text pb-2 text-balance text-[44px] leading-[1.05] font-medium tracking-[-0.035em] text-transparent sm:text-[72px]">
              {t('landing.tagline')}
            </h1>
            <p className="max-w-xl text-title-l text-on-surface-variant sm:text-[24px] sm:leading-[34px]">{t('landing.pitch', vars)}</p>
            <div className="mt-2 grid gap-3 sm:grid-cols-2">
              <Link
                to="/app"
                className="ripple group flex min-h-[88px] items-center gap-4 rounded-2xl bg-primary p-5 text-on-primary shadow-e1 transition-shadow hover:shadow-e3"
              >
                <span className="inline-flex size-12 shrink-0 items-center justify-center rounded-full bg-white/15">
                  <Icon name="mobile" />
                </span>
                <span className="flex flex-col text-left">
                  <span className="text-title-m">{t('landing.tryApp')}</span>
                  <span className="text-body-m opacity-90">{t('landing.tryAppHint')}</span>
                </span>
                <Icon name="arrow_forward" className="ml-auto transition-transform duration-300 ease-emphasized group-hover:translate-x-1" />
              </Link>
              <Link
                to="/console"
                className="ripple group flex min-h-[88px] items-center gap-4 rounded-2xl bg-secondary-container p-5 text-on-secondary-container transition-shadow hover:shadow-e2"
              >
                <span className="inline-flex size-12 shrink-0 items-center justify-center rounded-full bg-surface-container-lowest/60">
                  <Icon name="dashboard" />
                </span>
                <span className="flex flex-col text-left">
                  <span className="text-title-m">{t('landing.openConsole')}</span>
                  <span className="text-body-m opacity-90">{t('landing.openConsoleHint')}</span>
                </span>
                <Icon name="arrow_forward" className="ml-auto transition-transform duration-300 ease-emphasized group-hover:translate-x-1" />
              </Link>
            </div>
            <p className="flex items-start gap-2 text-body-m text-on-surface-variant">
              <Icon name="info" className="mt-0.5 size-[18px]" />
              {t('landing.sideBySide')}
            </p>
          </div>
          <Illustration verdictWord={t('customer.verdict.word.RED')} />
        </div>

        <figure className="rise-in grid items-center gap-6 rounded-[28px] bg-surface-container-lowest p-6 shadow-[0_0_0_1px_var(--outline-variant)] sm:p-10 md:grid-cols-[auto_minmax(0,1fr)] md:gap-12">
          <p className="text-[64px] leading-none font-medium tracking-[-0.04em] text-primary sm:text-[96px]">{t('landing.statValue')}</p>
          <div>
            <blockquote className="text-headline-s text-on-surface">{t('landing.stat')}</blockquote>
            <p className="mt-2 text-body-l text-on-surface-variant">{t('landing.statDetail')}</p>
            <figcaption className="mt-4">
              <a
                href={SOURCE_URL}
                target="_blank"
                rel="noreferrer noopener"
                className="ripple -ml-3 inline-flex min-h-10 items-center gap-1.5 rounded-full px-3 text-label-l font-medium text-primary"
              >
                {t('landing.source')}
                <Icon name="open_in_new" className="size-4" />
              </a>
            </figcaption>
          </div>
        </figure>

        <section aria-labelledby="how-title">
          <h2 id="how-title" className="text-headline-m text-on-surface">
            {t('landing.stepsTitle')}
          </h2>
          <ol className="stagger mt-6 grid gap-4 md:grid-cols-3">
            {STEPS.map(({ key, icon, shape, tone }, i) => (
              <li key={key} className="flex flex-col gap-4 rounded-[28px] bg-surface-container p-6">
                <Shape shape={shape} className={cn('size-16', tone)}>
                  <Icon name={icon} className="size-7" />
                </Shape>
                <span className="flex flex-col gap-1.5">
                  <span className="text-title-l text-on-surface">
                    <span className="text-on-surface-variant">{i + 1}. </span>
                    {t(`landing.steps.${key}.title`)}
                  </span>
                  <span className="text-body-l text-on-surface-variant">{t(`landing.steps.${key}.body`, vars)}</span>
                </span>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="stack-title" className="flex flex-col items-center gap-4 text-center">
          <h2 id="stack-title" className="flex items-center gap-2 text-title-m text-on-surface-variant">
            <Icon name="cloud" className="size-5" />
            {t('landing.builtOn')}
          </h2>
          <ul className="flex flex-wrap justify-center gap-2">
            {STACK.map((s) => (
              <li
                key={s.name}
                className="inline-flex h-10 items-center gap-2 rounded-full border border-outline-variant bg-surface-container-lowest px-4 text-label-l font-medium text-on-surface"
              >
                {s.icon === 'gemini' ? <Sparkle className="size-[18px]" /> : <Icon name={s.icon} className="size-[18px] text-primary" />}
                {s.name}
              </li>
            ))}
          </ul>
        </section>
      </main>

      <footer className="relative border-t border-outline-variant/60 px-5 py-6 text-center text-body-s text-on-surface-variant sm:px-8">
        {t('landing.footer')}
      </footer>
    </div>
  )
}

function Backdrop() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-0">
      <div className="absolute -top-56 -right-40 size-[760px] rounded-full bg-[radial-gradient(circle,rgb(66_133_244/0.18),transparent_62%)]" />
      <div className="absolute top-[30%] -left-64 size-[640px] rounded-full bg-[radial-gradient(circle,rgb(155_114_203/0.10),transparent_62%)]" />
      <div className="absolute inset-x-0 top-0 h-[720px] bg-[radial-gradient(rgb(31_31_31/0.07)_1px,transparent_1px)] [background-size:24px_24px] [mask-image:linear-gradient(to_bottom,#000,transparent)]" />
    </div>
  )
}

/**
 * The idea in one picture, language-neutral: the scammer's chat with numbered warning signs, the
 * customer's "On hold" verdict, and the case arriving in the analyst console.
 */
function Illustration({ verdictWord }: { verdictWord: string }) {
  const bubble = (w: string, flag?: number, mine = false) => (
    <div className={cn('relative flex', mine && 'justify-end')}>
      <div className={cn('flex flex-col gap-1.5 rounded-2xl px-3 py-2.5', mine ? 'rounded-tr-sm bg-[#D3E3FD]' : 'rounded-tl-sm bg-[#F0F4F9]')}>
        <span className={cn('h-2 rounded-full bg-[#1F1F1F]/25', w)} />
        <span className={cn('h-2 rounded-full bg-[#1F1F1F]/15', w === 'w-40' ? 'w-28' : 'w-20')} />
      </div>
      {flag && (
        <span className="absolute -inset-1 rounded-[18px] border-2 border-[#C5221F]">
          <span className="absolute -top-2.5 -left-2.5 inline-flex size-5 items-center justify-center rounded-full bg-[#C5221F] text-[11px] font-medium text-white shadow-[0_0_0_2px_#fff]">
            {flag}
          </span>
        </span>
      )}
    </div>
  )
  return (
    <div aria-hidden="true" className="relative mx-auto h-[460px] w-full max-w-[460px] select-none sm:h-[520px]">
      <Shape shape="cookie12" spin className="absolute top-6 left-1/2 size-[420px] -translate-x-1/2 text-[#D3E3FD]/70" />
      {/* the phone with the scam chat */}
      <div className="pop-in absolute top-4 left-2 w-[250px] rounded-[38px] bg-[#1B1B1F] p-2 shadow-e4 sm:left-6">
        <div className="flex h-[400px] flex-col gap-3 overflow-hidden rounded-[30px] bg-white px-4 pt-6 sm:h-[440px]">
          <div className="flex items-center gap-2 border-b border-[#E3E3E3] pb-3">
            <span className="size-8 rounded-full bg-[#4285F4]" />
            <span className="flex flex-col gap-1">
              <span className="h-2 w-20 rounded-full bg-[#1F1F1F]/40" />
              <span className="h-1.5 w-14 rounded-full bg-[#1F1F1F]/20" />
            </span>
          </div>
          {bubble('w-40', 1)}
          {bubble('w-32')}
          {bubble('w-24', undefined, true)}
          {bubble('w-40', 2)}
          {bubble('w-32', 3)}
        </div>
      </div>
      {/* the verdict the customer sees */}
      <div className="rise-in absolute right-0 bottom-6 w-[230px] rounded-3xl bg-[#FCE8E6] p-4 shadow-e3 [animation-delay:250ms] sm:bottom-10">
        <div className="flex items-center gap-3">
          <Shape shape="cookie12" className="size-12 text-[#D93025]">
            <Icon name="gpp_bad" fill className="size-6 text-white" />
          </Shape>
          <span className="flex flex-col">
            <span className="text-title-m text-[#8C1D18]">{verdictWord}</span>
            <span className="text-body-s text-[#8C1D18]/80 tabular-nums">S$8,000</span>
          </span>
        </div>
        <div className="mt-3 flex flex-col gap-1.5">
          <span className="h-2 w-full rounded-full bg-[#8C1D18]/20" />
          <span className="h-2 w-3/4 rounded-full bg-[#8C1D18]/20" />
        </div>
      </div>
      {/* the case arriving in the console */}
      <div className="rise-in absolute top-10 right-0 w-[220px] rounded-2xl bg-white p-3.5 shadow-e3 [animation-delay:450ms] sm:-right-2">
        <div className="flex items-center gap-2">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-[#1E8E3E] opacity-60 motion-reduce:hidden" />
            <span className="relative inline-flex size-2 rounded-full bg-[#1E8E3E]" />
          </span>
          <span className="h-2 w-16 rounded-full bg-[#1F1F1F]/20" />
          <Sparkle className="ml-auto size-4" />
        </div>
        <div className="mt-3 flex items-center gap-2.5">
          <span className="inline-flex size-9 items-center justify-center rounded-full bg-[#FCE8E6] text-[#C5221F]">
            <Icon name="gpp_bad" fill className="size-5" />
          </span>
          <span className="flex flex-1 flex-col gap-1.5">
            <span className="h-2 w-24 rounded-full bg-[#1F1F1F]/35" />
            <span className="h-1.5 w-16 rounded-full bg-[#1F1F1F]/20" />
          </span>
          <span className="text-label-l font-medium text-[#1F1F1F] tabular-nums">S$8,000</span>
        </div>
      </div>
    </div>
  )
}
