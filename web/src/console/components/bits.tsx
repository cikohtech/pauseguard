import type { ReactNode } from 'react'

import type { CaseStatus } from '@/console/api'
import { STATUS_LABEL, TYPOLOGY_LABEL, VERDICT_ICON, percent } from '@/console/format'
import { Icon, Sparkle, type IconName } from '@/components/icons/Icon'
import type { Typology, Verdict } from '@/lib/api'
import { cn } from '@/lib/utils'

const VERDICT_STYLE: Record<Verdict, string> = {
  RED: 'bg-verdict-red-soft text-verdict-red-ink',
  AMBER: 'bg-verdict-amber-soft text-verdict-amber-ink',
  GREEN: 'bg-verdict-green-soft text-verdict-green-ink',
}

/** Colour is never alone: icon + word (UI_SPEC design system). */
export function VerdictBadge({ verdict, size = 'sm' }: { verdict: Verdict; size?: 'sm' | 'lg' }) {
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-sm font-medium tracking-wide',
        size === 'lg' ? 'h-8 px-3 text-label-l' : 'h-6 px-2 text-label-m',
        VERDICT_STYLE[verdict],
      )}
    >
      <Icon name={VERDICT_ICON[verdict]} fill className={size === 'lg' ? 'size-[18px]' : 'size-4'} />
      {verdict}
    </span>
  )
}

export function TypologyChip({ typology, className }: { typology: Typology; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex h-6 max-w-full items-center truncate rounded-sm border border-outline-variant px-2 text-label-m font-medium text-on-surface-variant',
        className,
      )}
    >
      {TYPOLOGY_LABEL[typology]}
    </span>
  )
}

export function StatusBadge({ status }: { status: CaseStatus }) {
  return (
    <span
      className={cn(
        'inline-flex h-8 items-center gap-1.5 rounded-sm px-3 text-label-l font-medium',
        status === 'OPEN' ? 'bg-primary-container text-on-primary-container' : 'bg-surface-container-high text-on-surface',
      )}
    >
      <Icon name={status === 'OPEN' ? 'inbox' : 'task_alt'} className="size-[18px]" />
      {STATUS_LABEL[status]}
    </span>
  )
}

/** A meter: the fill carries the value, the track is a lighter step of the same hue (M3 linear). */
export function ConfidenceBar({ value, label = 'Confidence', className }: { value: number; label?: string; className?: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100)
  return (
    <span className={cn('inline-flex items-center gap-2', className)}>
      <span
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={percent(value)}
        className="relative flex h-1 w-20 items-center gap-1"
      >
        <span className="h-1 rounded-full bg-primary" style={{ width: `${pct}%` }} />
        {pct < 100 && <span className="h-1 flex-1 rounded-full bg-primary-container" />}
      </span>
      <span className="text-label-m text-on-surface-variant tabular-nums">{percent(value)}</span>
    </span>
  )
}

export function Kbd({ children, className }: { children: string; className?: string }) {
  return (
    <kbd
      aria-hidden="true"
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded-xs border border-current/30 px-1 font-mono text-[11px] font-medium uppercase opacity-80',
        className,
      )}
    >
      {children}
    </kbd>
  )
}

/** A titled card inside a tab (GM3 outlined card). */
export function Section({
  title,
  icon,
  children,
  className,
  aside,
}: {
  title: string
  icon?: IconName
  children: ReactNode
  className?: string
  aside?: ReactNode
}) {
  return (
    <section className={cn('rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5', className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-title-m text-on-surface">
          {icon && <Icon name={icon} className="size-5 text-on-surface-variant" />}
          {title}
        </h3>
        {aside}
      </div>
      {children}
    </section>
  )
}

/** The label Google products put on AI output: a sparkle and who wrote it. */
export function AiLabel({ children = 'Gemini' }: { children?: ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-surface-container px-2.5 py-1 text-label-m font-medium text-on-surface-variant">
      <Sparkle className="size-3.5" />
      {children}
    </span>
  )
}
