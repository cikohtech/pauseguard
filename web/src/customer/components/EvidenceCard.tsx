import { FileText } from 'lucide-react'
import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import {
  boxToPercent,
  explanationFor,
  flagsBySource,
  highlightQuotes,
  type EvidenceSource,
  type NumberedFlag,
} from '@/customer/evidence'
import type { CustomerMessage, RedFlag, Verdict } from '@/lib/api'
import { cn } from '@/lib/utils'

// The evidence card (UI_SPEC Area 1, screen 7): the customer's own screenshot with numbered boxes
// on the warning signs (from Gemini's box_2d), the pasted chat with the quotes marked, and the
// numbered explanations below. Box n, mark n and list item n are the same flag.

const INK: Record<Verdict, string> = {
  GREEN: 'bg-verdict-green-ink',
  AMBER: 'bg-verdict-amber-ink',
  RED: 'bg-verdict-red-ink',
}
const BORDER: Record<Verdict, string> = {
  GREEN: 'border-verdict-green-ink',
  AMBER: 'border-verdict-amber-ink',
  RED: 'border-verdict-red-ink',
}
const SOFT: Record<Verdict, string> = {
  GREEN: 'bg-verdict-green-soft',
  AMBER: 'bg-verdict-amber-soft',
  RED: 'bg-verdict-red-soft',
}

function Marker({ n, verdict, className }: { n: number; verdict: Verdict; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-flex size-6 shrink-0 items-center justify-center rounded-full text-[13px] font-bold text-white shadow-[0_0_0_2px_#fff]',
        INK[verdict],
        className,
      )}
    >
      {n}
    </span>
  )
}

export function EvidenceCard({
  flags,
  message,
  sources,
  verdict,
}: {
  flags: RedFlag[]
  message: CustomerMessage | null
  sources: EvidenceSource[]
  verdict: Verdict
}) {
  const { t } = useTranslation()
  const id = useId()
  const [active, setActive] = useState<number | null>(null)
  const { numbered, perSource } = flagsBySource(flags, sources)
  if (numbered.length === 0) return null

  const title = (f: NumberedFlag) => t(`customer.flags.${f.flag.code}`, { defaultValue: f.flag.code })
  const itemId = (n: number) => `${id}-flag-${n}`

  return (
    <section aria-labelledby={`${id}-title`} className="rounded-2xl border border-border bg-card p-4 shadow-sm">
      <h2 id={`${id}-title`} className="text-[17px] font-semibold">
        {t('customer.verdict.evidenceTitle')}
      </h2>
      <p className="mt-0.5 text-sm text-muted-foreground">{t('customer.verdict.evidenceHint')}</p>

      {perSource.map(({ source, index, flags: here }) => {
        if (source.kind === 'image') {
          const boxed = here
            .map((f) => ({ f, box: boxToPercent(f.flag.box_2d) }))
            .filter((b) => b.box !== null)
          return (
            <div key={index} className="mt-4 flex justify-center">
              <div className="relative inline-block max-w-full">
                <img
                  src={source.url}
                  alt={t('customer.verdict.imageAlt', { name: source.name, count: boxed.length })}
                  className="block max-h-[460px] w-auto max-w-full rounded-lg border border-border"
                />
                {boxed.map(({ f, box }) => (
                  <button
                    key={f.n}
                    type="button"
                    data-testid={`flag-box-${f.n}`}
                    aria-label={t('customer.verdict.boxLabel', { n: f.n, title: title(f) })}
                    aria-describedby={itemId(f.n)}
                    aria-pressed={active === f.n}
                    onClick={() => setActive(active === f.n ? null : f.n)}
                    style={{
                      top: `${box!.top}%`,
                      left: `${box!.left}%`,
                      width: `${box!.width}%`,
                      height: `${box!.height}%`,
                    }}
                    className={cn(
                      'absolute rounded-md border-[2.5px] shadow-[0_0_0_1.5px_rgba(255,255,255,0.9)] outline-none transition-[background-color,box-shadow] focus-visible:ring-3 focus-visible:ring-ring',
                      BORDER[verdict],
                      active === f.n ? 'bg-black/10 ring-3 ring-ring/40' : 'bg-transparent',
                    )}
                  >
                    <Marker n={f.n} verdict={verdict} className="absolute -top-3 -left-3" />
                  </button>
                ))}
              </div>
            </div>
          )
        }
        if (source.kind === 'text' && here.length > 0) {
          return (
            <figure key={index} className="mt-4">
              <figcaption className="mb-1.5 text-sm font-medium text-muted-foreground">
                {t('customer.verdict.pasted')}
              </figcaption>
              <blockquote className="rounded-xl bg-muted px-3.5 py-3 text-[15px] leading-relaxed whitespace-pre-wrap">
                {highlightQuotes(source.text, here).map((seg, i) =>
                  seg.n ? (
                    <mark
                      key={i}
                      className={cn(
                        'rounded px-0.5 text-foreground ring-1 ring-current/20 [box-decoration-break:clone]',
                        SOFT[verdict],
                        active === seg.n && 'ring-2 ring-ring',
                      )}
                    >
                      <Marker n={seg.n} verdict={verdict} className="mr-1 size-5 align-[-3px] text-[11px]" />
                      <span className="sr-only">
                        {t('customer.verdict.boxLabel', { n: seg.n, title: title({ n: seg.n, flag: numbered[seg.n - 1].flag }) })}:
                      </span>
                      {seg.text}
                    </mark>
                  ) : (
                    <span key={i}>{seg.text}</span>
                  ),
                )}
              </blockquote>
            </figure>
          )
        }
        if (source.kind === 'pdf') {
          return (
            <p key={index} className="mt-4 flex items-center gap-2 rounded-xl bg-muted px-3 py-2.5 text-sm">
              <FileText aria-hidden="true" className="size-5 text-muted-foreground" />
              <span className="truncate font-medium">{source.name}</span>
              <span className="text-muted-foreground">· {t('customer.verdict.pdf')}</span>
            </p>
          )
        }
        return null
      })}

      <ol className="mt-4 flex flex-col gap-2">
        {numbered.map((f, i) => {
          const text = explanationFor(message, f.flag, i)
          return (
            <li key={f.n}>
              <button
                type="button"
                id={itemId(f.n)}
                onClick={() => setActive(active === f.n ? null : f.n)}
                aria-pressed={active === f.n}
                className={cn(
                  'flex w-full gap-3 rounded-xl p-3 text-left outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50',
                  active === f.n ? SOFT[verdict] : 'hover:bg-muted',
                )}
              >
                <Marker n={f.n} verdict={verdict} className="mt-0.5" />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="font-semibold">{title(f)}</span>
                  {text && <span className="text-[15px] leading-snug">{text}</span>}
                  {f.flag.quote && (
                    <span className="text-sm break-words text-muted-foreground italic">“{f.flag.quote}”</span>
                  )}
                </span>
              </button>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
