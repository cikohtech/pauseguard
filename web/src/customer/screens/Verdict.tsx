import {
  CircleCheckBig,
  Clock,
  Phone,
  PhoneCall,
  ShieldAlert,
  ShieldX,
  UserRoundSearch,
} from 'lucide-react'
import { useEffect, useEffectEvent, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Navigate, useNavigate } from 'react-router-dom'

import { EvidenceCard } from '@/customer/components/EvidenceCard'
import { FeedbackThumbs } from '@/customer/components/FeedbackThumbs'
import { usePortalContainer } from '@/customer/portal'
import { HarbourLogo, LangSwitch, Screen } from '@/customer/components/Screen'
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

const LOOK: Record<VerdictKind, { icon: typeof ShieldX; soft: string; ink: string; solid: string }> = {
  GREEN: { icon: CircleCheckBig, soft: 'bg-verdict-green-soft', ink: 'text-verdict-green-ink', solid: 'bg-verdict-green' },
  AMBER: { icon: ShieldAlert, soft: 'bg-verdict-amber-soft', ink: 'text-verdict-amber-ink', solid: 'bg-verdict-amber' },
  RED: { icon: ShieldX, soft: 'bg-verdict-red-soft', ink: 'text-verdict-red-ink', solid: 'bg-verdict-red' },
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
  const Icon = look.icon
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
      <div className="flex flex-col gap-2">
        <div aria-hidden="true" className="h-1 overflow-hidden rounded-full bg-muted">
          <div className="h-full origin-left animate-[grow_2s_linear_forwards] rounded-full bg-verdict-green motion-reduce:animate-none" />
        </div>
        <button type="button" disabled={busy} onClick={() => void finish('PROCEEDED')} className={bigButton()}>
          {busy ? t('customer.verdict.continuing') : t('customer.verdict.continueNow')}
        </button>
      </div>
    ) : verdict === 'AMBER' ? (
      <div className="flex flex-col gap-2">
        <button type="button" disabled={busy} onClick={() => void finish('COOL_OFF')} className={bigButton()}>
          <Clock aria-hidden="true" />
          {t('customer.verdict.pause')}
        </button>
        <a href={tel} onClick={calledContact} className={bigButton('outline')}>
          <PhoneCall aria-hidden="true" />
          {t('customer.verdict.callContact', { contact })}
        </a>
      </div>
    ) : (
      <div className="flex flex-col gap-2">
        <a href={tel} onClick={calledContact} className={bigButton()}>
          <PhoneCall aria-hidden="true" />
          {t('customer.verdict.callContact', { contact })}
        </a>
        <a href="tel:1799" className={bigButton('outline')}>
          <Phone aria-hidden="true" />
          {t('customer.verdict.call1799')}
        </a>
      </div>
    )

  return (
    <Screen
      header={
        <header className={cn('pt-sat shrink-0', look.soft)}>
          <div className="flex h-14 items-center justify-between px-5">
            <HarbourLogo />
            <LangSwitch />
          </div>
        </header>
      }
      footer={footer}
      className={cn(verdict === 'GREEN' && 'flex flex-col', look.soft)}
    >
      <div
        data-testid={`verdict-${verdict}`}
        className={cn(
          'px-5 pt-2 pb-6 text-center',
          look.soft,
          // GREEN has nothing below the hero: centre it on the screen
          verdict === 'GREEN' && 'flex flex-1 flex-col justify-center pb-24',
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            'mx-auto flex size-20 items-center justify-center rounded-full text-white shadow-lg motion-safe:animate-in motion-safe:zoom-in-75 motion-safe:duration-300',
            look.solid,
          )}
        >
          <Icon className="size-11" strokeWidth={2} />
        </span>
        {verdict !== 'GREEN' && (
          // the verdict as a word next to the colour (GREEN's headline already is the word)
          <p className={cn('mt-3 flex items-center justify-center gap-1.5 text-sm font-bold tracking-wide uppercase', look.ink)}>
            <Icon aria-hidden="true" className="size-4" />
            {word}
          </p>
        )}
        <h1 ref={heading} tabIndex={-1} className="mt-1 text-[24px] leading-tight font-semibold outline-none">
          {msg?.headline ?? word}
        </h1>
        {msg?.body && <p className="mt-2 text-[16px] leading-relaxed text-foreground/90">{msg.body}</p>}
        {transfer && (
          <p className="mt-3 text-sm text-muted-foreground">
            {amount} → {transfer.payee_name}
          </p>
        )}
        <p role="status" className="sr-only">
          {t('customer.verdict.announce', { word, headline: msg?.headline ?? '' })}
        </p>
      </div>

      <div className={cn('flex flex-col gap-4 bg-background px-5 pt-4 pb-4', verdict === 'GREEN' && 'hidden')}>
        {verdict === 'RED' && (
          <p className="flex items-start gap-3 rounded-2xl bg-verdict-red-soft p-4 text-left text-[15px] leading-snug text-verdict-red-ink">
            <Phone aria-hidden="true" className="mt-0.5 size-5 shrink-0" />
            {t('customer.verdict.fraudTeam')}
          </p>
        )}
        {result.needs_review && verdict !== 'RED' && (
          <p className="flex items-start gap-3 rounded-2xl bg-muted p-4 text-[15px] leading-snug">
            <UserRoundSearch aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-muted-foreground" />
            {t('customer.verdict.review')}
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
              <DialogHeader>
                <DialogTitle>{t('customer.verdict.confirm.title')}</DialogTitle>
                <DialogDescription className="text-[15px] leading-relaxed text-foreground/85">
                  {t('customer.verdict.confirm.body', {
                    contact: t(`customer.personas.${p.customer_id}.contactYour`),
                  })}
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
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
