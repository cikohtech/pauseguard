import { Table2 } from 'lucide-react'
import { useId, useState, type ReactNode } from 'react'

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
    <section aria-labelledby={`${id}-t`} className={cn('flex flex-col rounded-xl border border-border bg-card p-4', className)}>
      <div className="mb-3 flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <h3 id={`${id}-t`} className="text-sm font-semibold">
            {title}
          </h3>
          {subtitle && <p className="mt-0.5 text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        <button
          type="button"
          onClick={() => setAsTable(!asTable)}
          aria-pressed={asTable}
          aria-label={`Table view of ${title}`}
          className="inline-flex min-h-9 shrink-0 items-center gap-1.5 rounded-lg border border-border px-2.5 text-xs font-medium text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50 aria-pressed:border-primary/40 aria-pressed:bg-primary-soft aria-pressed:text-primary"
        >
          <Table2 aria-hidden="true" className="size-3.5" />
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
    <ul className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
      {items.map((i) => (
        <li key={i.label} className="inline-flex items-center gap-1.5">
          <span aria-hidden="true" className="size-2.5 rounded-[3px]" style={{ background: i.color }} />
          {i.label}
        </li>
      ))}
    </ul>
  )
}

/** Recharts tooltip body: a small card in text colours with a swatch per series. */
export function TooltipCard({ title, rows }: { title: string; rows: { label: string; value: string; color?: string }[] }) {
  return (
    <div className="rounded-lg border border-border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-semibold text-foreground">{title}</p>
      {rows.map((r) => (
        <p key={r.label} className="flex items-center gap-1.5 text-muted-foreground">
          {r.color && <span aria-hidden="true" className="size-2 rounded-[2px]" style={{ background: r.color }} />}
          <span>{r.label}</span>
          <span className="ml-auto pl-3 font-semibold text-foreground tabular-nums">{r.value}</span>
        </p>
      ))}
    </div>
  )
}

export function DataTable({ head, rows }: { head: string[]; rows: ReactNode[][] }) {
  return (
    <table className="w-full text-left text-sm">
      <thead className="sticky top-0 bg-card text-xs text-muted-foreground">
        <tr>
          {head.map((h, i) => (
            <th key={h} scope="col" className={cn('py-1.5 font-medium', i > 0 && 'text-right')}>
              {h}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => (
          <tr key={i} className="border-t border-border">
            {r.map((cell, j) => (
              <td key={j} className={cn('py-1.5', j > 0 && 'text-right tabular-nums')}>
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}
