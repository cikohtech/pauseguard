import { ShieldAlert, ShieldCheck, TriangleAlert } from 'lucide-react'

import type { CaseStatus } from '@/console/api'
import { STATUS_LABEL, TYPOLOGY_LABEL, percent } from '@/console/format'
import type { Typology, Verdict } from '@/lib/api'
import { cn } from '@/lib/utils'

const VERDICT_STYLE: Record<Verdict, string> = {
  RED: 'bg-verdict-red-soft text-verdict-red-ink',
  AMBER: 'bg-verdict-amber-soft text-verdict-amber-ink',
  GREEN: 'bg-verdict-green-soft text-verdict-green-ink',
}
const VERDICT_ICON = { RED: ShieldAlert, AMBER: TriangleAlert, GREEN: ShieldCheck }

/** Colour is never alone: icon + word (UI_SPEC design system). */
export function VerdictBadge({ verdict, size = 'sm' }: { verdict: Verdict; size?: 'sm' | 'lg' }) {
  const Icon = VERDICT_ICON[verdict]
  return (
    <span
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full font-semibold tracking-wide',
        size === 'lg' ? 'px-3 py-1 text-sm' : 'px-2 py-0.5 text-xs',
        VERDICT_STYLE[verdict],
      )}
    >
      <Icon aria-hidden="true" className={size === 'lg' ? 'size-4' : 'size-3.5'} />
      {verdict}
    </span>
  )
}

export function TypologyChip({ typology, className }: { typology: Typology; className?: string }) {
  return (
    <span
      className={cn(
        'inline-flex max-w-full items-center truncate rounded-md bg-secondary px-2 py-0.5 text-xs font-medium text-secondary-foreground',
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
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium',
        status === 'OPEN' ? 'border-primary/30 text-primary' : 'border-border bg-muted text-foreground',
      )}
    >
      {STATUS_LABEL[status]}
    </span>
  )
}

/** A meter: the fill carries the value, the track is a lighter step of the same hue. */
export function ConfidenceBar({ value, label = 'Confidence' }: { value: number; label?: string }) {
  const pct = Math.round(Math.min(1, Math.max(0, value)) * 100)
  return (
    <span className="inline-flex items-center gap-2">
      <span
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct}
        aria-valuetext={percent(value)}
        className="relative h-1.5 w-20 overflow-hidden rounded-full bg-primary-soft"
      >
        <span className="absolute inset-y-0 left-0 rounded-full bg-primary" style={{ width: `${pct}%` }} />
      </span>
      <span className="text-xs text-muted-foreground tabular-nums">{percent(value)}</span>
    </span>
  )
}

export function Kbd({ children, className }: { children: string; className?: string }) {
  return (
    <kbd
      aria-hidden="true"
      className={cn(
        'inline-flex h-5 min-w-5 items-center justify-center rounded border border-current/25 px-1 font-sans text-[11px] font-semibold uppercase opacity-80',
        className,
      )}
    >
      {children}
    </kbd>
  )
}

/** A titled block inside a tab. */
export function Section({
  title,
  children,
  className,
  aside,
}: {
  title: string
  children: React.ReactNode
  className?: string
  aside?: React.ReactNode
}) {
  return (
    <section className={cn('rounded-xl border border-border bg-card p-4', className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold">{title}</h3>
        {aside}
      </div>
      {children}
    </section>
  )
}
