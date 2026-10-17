import { useId, useState, type ReactNode } from 'react'

import { Icon } from '@/components/icons/Icon'
import { cn } from '@/lib/utils'

// Shared chart chrome for the console (Recharts). Colours are CSS tokens (index.css, "chart"):
// the verdict series use GREEN, AMBER and the darker RED ink, which pass the palette validator as
// neighbours in a stack (raw AMBER↔RED are too close); single series use the primary teal, and
// emphasis charts grey the context. Every chart has a table view, so no value hides behind colour
// or hover.

export function ChartCard({
  title,
  subtitle,
  chart,
  table,
  legend,
  className,
  height = 220,
}: {
  title: string
  subtitle?: ReactNode
  chart: ReactNode
  table: ReactNode
  legend?: ReactNode
  className?: string
  height?: number
}) {
  const [asTable, setAsTable] = useState(false)
  const id = useId()
  return (
    <section aria-labelledby={`${id}-t`} className={cn('flex flex-col rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5', className)}>
      <div className="mb-4 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 id={`${id}-t`} className="text-title-m text-on-surface">
            {title}
          </h3>
          {subtitle && <p className="mt-0.5 text-body-s text-on-surface-variant">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={() => setAsTable(!asTable)}
          aria-pressed={asTable}
          aria-label={`Table view of ${title}`}
          className="ripple inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-sm border border-outline-variant px-3 text-label-l font-medium text-on-surface-variant aria-pressed:border-transparent aria-pressed:bg-secondary-container aria-pressed:text-on-secondary-container"
        >
          <Icon name={asTable ? 'check' : 'table'} className="size-[18px]" />
          Table
        </button>
      </div>
      {legend && !asTable && <div className="mb-2">{legend}</div>}
      {asTable ? (
        <div
          role="region"
          aria-label={`${title}, table`}
          tabIndex={0}
          className="max-h-[320px] overflow-auto rounded-md outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {table}
        </div>
      ) : (
        <div style={{ height }} className="w-full min-w-0">
          {chart}
        </div>
      )}
    </section>
  )
}

/** Legend for two or more series: a swatch beside text in text colour, never coloured text. */
export function Legend({ items }: { items: { label: string; color: string }[] }) {
  return (
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-body-s text-on-surface-variant">
      {items.map((i) => (
        <li key={i.label} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="size-3 rounded-full" style={{ background: i.color }} />
          {i.label}
        </li>
      ))}
    </ul>
  )
}

/** Recharts tooltip body: a small card in text colours with a swatch per series. */
export function TooltipCard({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="min-w-36 rounded-md bg-surface-container-lowest px-3 py-2.5 text-body-s shadow-e2">
      <p className="mb-1 text-label-l font-medium text-on-surface">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center gap-1.5 text-on-surface-variant">
          {r.color && <span aria-hidden="true" className="size-2.5 rounded-full" style={{ background: r.color }} />}
          <span>{r.label}</span>
          <span className="ml-auto pl-3 font-medium text-on-surface tabular-nums">{r.value}</span>
        </p>
      ))}
    </div>
  )
}

export function DataTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <table className="w-full text-left text-body-m">
      <thead className="sticky top-0 bg-surface-container-low text-label-l text-on-surface-variant">
        <tr>
          {head.map((h, i) => (
            <th key={h} scope="col" className={cn('h-10 px-3 font-medium', i > 0 && 'text-right')}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-t border-outline-variant/60">
            {r.map((cell, j) => (
              <td key={j} className={cn('h-10 px-3', j > 0 && 'text-right tabular-nums')}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
