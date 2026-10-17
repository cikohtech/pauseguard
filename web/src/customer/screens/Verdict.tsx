import { useEffect, useEffectEvent, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate } from 'react-router-dom'

import { Icon, type IconName } from '@/components/icons/Icon'
import { Shape, WavyProgress, type ShapeName } from '@/components/m3/Expressive'
import { EvidenceCard } from '@/customer/components/EvidenceCard'
import { FeedbackThumbs } from '@/customer/components/FeedbackThumbs'
import { usePortalContainer } from '@/customer/portal'
import { HarbourLogo, Screen } from '@/customer/components/Screen'
import type { DemoPersona } from '@/customer/demo'
import { formatSgd } from '@/customer/format'
import { useSession } from '@/customer/session'
import { bigButton } from '@/customer/styles'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { api, type CheckResult, type Verdict as VerdictKind } from '@/lib/api'
import { cn } from '@/lib/utils'

const GREEN_AUTO_CONTINUE_MS = 2000

// Each verdict has its own colour, icon, word *and* M3 Expressive shape, so it never rests on
// colour alone: a sunny check for GREEN, a six-point cookie for AMBER, a calm scalloped shield
// for RED.
const LOOK: Record<VerdictKind, { icon: IconName; shape: ShapeName; soft: string; ink: string; solid: string }> = {
  GREEN: { icon: 'check_circle', shape: 'sunny', soft: 'bg-verdict-green-soft', ink: 'text-verdict-green-ink', solid: 'text-verdict-green' },
  AMBER: { icon: 'gpp_maybe', shape: 'cookie6', soft: 'bg-verdict-amber-soft', ink: 'text-verdict-amber-ink', solid: 'text-verdict-amber' },
  RED: { icon: 'gpp_bad', shape: 'cookie12', soft: 'bg-verdict-red-soft', ink: 'text-verdict-red-ink', solid: 'text-verdict-red' },
}

/** Screen 7: the GREEN / AMBER / RED verdict for the check (POST /messages response). */
export function Verdict() {
  const { check } = useSession()
  if (!check?.result?.verdict) return <Navigate to="/app/home" replace />
  return <VerdictView result={check.result} verdict={check.result.verdict} />
}

export function VerdictView({ result, verdict }: { result: CheckResult; verdict: VerdictKind }) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const container = usePortalContainer()
  const { persona, transfer, check, setOutcome, recordSent, resetFlow } = useSession()
  const p = persona as DemoPersona
  const heading = useRef<HTMLHeadingElement>(null)
  const [busy, setBusy] = useState(false)
  const look = LOOK[verdict]
  const msg = result.customer_message
  const word = t(`customer.verdict.word.${verdict}`)
  const contact = t(`customer.personas.${p.customer_id}.contact`)
  const amount = transfer ? formatSgd(transfer.amount) : ''
  const tel = `tel:${p.trustedPhone.replace(/\s/g, '')}`

  useEffect(() => {
    heading.current?.focus()
  }, [])

  const finish = async (choice: 'PROCEEDED' | 'COOL_OFF', confirmed = false) => {
    setBusy(true)
    try {
      await api.choice(result.check_id, choice, confirmed)
    } catch {
      // the choice is recorded best effort; the customer's decision stands in the app
    }
    if (choice === 'PROCEEDED' && transfer) recordSent(transfer)
    setOutcome(choice === 'PROCEEDED' ? 'sent' : 'paused')
    navigate('/app/done')
  }

  // GREEN: "Looks good. Your transfer is on its way." and continue after 2 s.
  const autoContinue = useEffectEvent(() => void finish('PROCEEDED'))
  useEffect(() => {
    if (verdict !== 'GREEN') return
    const timer = setTimeout(autoContinue, GREEN_AUTO_CONTINUE_MS)
    return () => clearTimeout(timer)
  }, [verdict])

  const calledContact = () => {
    api.choice(result.check_id, 'CALLED_CONTACT').catch(() => {})
  }

  const goHome = () => {
    resetFlow()
    navigate('/app/home')
  }

  const footer =
    verdict === 'GREEN' ? (
      <div className="flex flex-col gap-3">
        <WavyProgress durationMs={GREEN_AUTO_CONTINUE_MS} className="text-verdict-green" />
        <button type="button" disabled={busy} onClick={() => void finish('PROCEEDED')} className={bigButton()}>
          {busy ? t('customer.verdict.continuing') : t('customer.verdict.continueNow')}
        </button>
      </div>
    ) : verdict === 'AMBER' ? (
      <div className="flex flex-col gap-2">
        <button type="button" disabled={busy} onClick={() => void finish('COOL_OFF')} className={bigButton()}>
          <Icon name="schedule" />
          {t('customer.verdict.pause')}
        </button>
        <a href={tel} onClick={calledContact} className={bigButton('tonal')}>
          <Icon name="call" fill />
          {t('customer.verdict.callContact', { contact })}
        </a>
      </div>
    ) : (
      <div className="flex flex-col gap-2">
        <a href={tel} onClick={calledContact} className={bigButton()}>
          <Icon name="call" fill />
          {t('customer.verdict.callContact', { contact })}
        </a>
        <a href="tel:1799" className={bigButton('outline')}>
          <Icon name="phone_in_talk" />
          {t('customer.verdict.call1799')}
        </a>
      </div>
    )

  return (
    <Screen
      header={
        <header className={cn('pt-sat shrink-0', look.soft)}>
          <div className="flex h-16 items-center pl-5">
            <HarbourLogo />
          </div>
        </header>
      }
      footer={footer}
      className={cn(verdict === 'GREEN' ? cn('flex flex-col', look.soft) : 'bg-surface')}
    >
      <div
        data-testid={`verdict-${verdict}`}
        className={cn(
          'rounded-b-[32px] px-6 pt-3 pb-7 text-center',
          look.soft,
          // GREEN has nothing below the hero: centre it on the screen
          verdict === 'GREEN' && 'flex flex-1 flex-col justify-center rounded-none pb-24',
        )}
      >
        <Shape shape={look.shape} spin className={cn('pop-in mx-auto flex size-28', look.solid)}>
          <Icon name={look.icon} fill className="size-14 text-white" />
        </Shape>
        {verdict !== 'GREEN' && (
          // the verdict as a word next to the colour (GREEN's headline already is the word)
          <p className="rise-in mt-4">
            <span
              className={cn(
                'inline-flex items-center gap-1.5 rounded-full bg-surface-container-lowest/80 px-3 py-1 text-label-l font-semibold',
                look.ink,
              )}
            >
              <Icon name={look.icon} fill className="size-[18px]" />
              {word}
            </span>
          </p>
        )}
        <h1 ref={heading} tabIndex={-1} className="rise-in mt-3 text-headline-m text-balance outline-none">
          {msg?.headline ?? word}
        </h1>
        {msg?.body && <p className="rise-in mt-2 text-body-l text-on-surface/90">{msg.body}</p>}
        {transfer && (
          <p className="mx-auto mt-4 inline-flex max-w-full items-center gap-2 rounded-full bg-surface-container-lowest/70 px-4 py-2 text-body-m text-on-surface-variant">
            <span className="font-medium text-on-surface tabular-nums">{amount}</span>
            <Icon name="arrow_forward" className="size-4" />
            <span className="truncate">{transfer.payee_name}</span>
          </p>
        )}
        <p role="status" className="sr-only">
          {t('customer.verdict.announce', { word, headline: msg?.headline ?? '' })}
        </p>
      </div>

      <div className={cn('stagger flex flex-col gap-3 px-4 pt-4 pb-4', verdict === 'GREEN' && 'hidden')}>
        {verdict === 'RED' && (
          <p className="flex items-start gap-3 rounded-xl bg-surface-container-low p-4 text-left text-body-l text-on-surface">
            <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-verdict-red-soft text-verdict-red-ink">
              <Icon name="phone_in_talk" className="size-5" />
            </span>
            {t('customer.verdict.fraudTeam')}
          </p>
        )}
        {result.needs_review && verdict !== 'RED' && (
          <p className="flex items-start gap-3 rounded-xl bg-surface-container-low p-4 text-body-l">
            <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container">
              <Icon name="person_search" className="size-5" />
            </span>
            <span className="pt-2">{t('customer.verdict.review')}</span>
          </p>
        )}
        {verdict !== 'GREEN' && (
          <EvidenceCard
            flags={result.top_flags}
            message={msg}
            sources={check?.evidence ?? []}
            verdict={verdict}
          />
        )}

        {verdict === 'AMBER' && (
          <Dialog>
            <DialogTrigger className={bigButton('quiet')}>{t('customer.verdict.proceed')}</DialogTrigger>
            <DialogContent container={container}>
              <DialogHeader className="items-center text-center">
                <Icon name="warning" className="size-6 text-verdict-amber-ink" />
                <DialogTitle>{t('customer.verdict.confirm.title')}</DialogTitle>
                <DialogDescription className="text-body-l text-on-surface-variant">
                  {t('customer.verdict.confirm.body', {
                    contact: t(`customer.personas.${p.customer_id}.contactYour`),
                  })}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter className="mt-2">
                <DialogClose className={bigButton()}>
                  {t('customer.verdict.confirm.cancel')}
                </DialogClose>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void finish('PROCEEDED', true)}
                  className={bigButton('outline')}
                >
                  {t('customer.verdict.confirm.confirm', { amount })}
                </button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        )}
        {verdict === 'RED' && (
          <button type="button" onClick={goHome} className={bigButton('quiet')}>
            {t('customer.verdict.home')}
          </button>
        )}
        {verdict !== 'GREEN' && <FeedbackThumbs checkId={result.check_id} />}
      </div>
    </Screen>
  )
}
