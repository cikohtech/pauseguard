import { useId, useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Icon } from '@/components/icons/Icon'
import {
  boxToPercent,
  explanationFor,
  flagsBySource,
  highlightQuotes,
  type EvidenceSource,
  type NumberedFlag,
} from '@/customer/evidence'
import type { CustomerMessage, RedFlag, RedFlagCode, Verdict } from '@/lib/api'
import { cn } from '@/lib/utils'

// The evidence card (UI_SPEC Area 1, screen 7): the customer's own screenshot with numbered boxes
// on the warning signs (from Gemini's box_2d), the pasted chat with the quotes marked, and the
// numbered explanations below. Box n, mark n and list item n are the same flag. The analyst
// console reuses it with its own wording (`copy`) and the flags' severities.

/** The card's wording; the customer app's (i18n) is the default. */
export interface EvidenceCopy {
  title: string
  hint: string
  pasted: string
  pdf: string
  imageAlt: (name: string, count: number) => string
  boxLabel: (n: number, title: string) => string
  flagTitle: (code: RedFlagCode) => string
}

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
        'inline-flex size-6 shrink-0 items-center justify-center rounded-full text-[13px] font-semibold text-white tabular-nums shadow-[0_0_0_2px_#fff,0_1px_3px_rgb(0_0_0/0.3)]',
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
  copy: custom,
  showSeverity = false,
}: {
  flags: RedFlag[]
  message: CustomerMessage | null
  sources: EvidenceSource[]
  verdict: Verdict
  copy?: EvidenceCopy
  showSeverity?: boolean
}) {
  const { t } = useTranslation()
  const id = useId()
  const [active, setActive] = useState<number | null>(null)
  const { numbered, perSource } = flagsBySource(flags, sources)
  if (numbered.length === 0) return null

  const copy: EvidenceCopy = custom ?? {
    title: t('customer.verdict.evidenceTitle'),
    hint: t('customer.verdict.evidenceHint'),
    pasted: t('customer.verdict.pasted'),
    pdf: t('customer.verdict.pdf'),
    imageAlt: (name, count) => t('customer.verdict.imageAlt', { name, count }),
    boxLabel: (n, title) => t('customer.verdict.boxLabel', { n, title }),
    flagTitle: (code) => t(`customer.flags.${code}`, { defaultValue: code }),
  }
  const title = (f: NumberedFlag) => copy.flagTitle(f.flag.code)
  const itemId = (n: number) => `${id}-flag-${n}`

  return (
    <section aria-labelledby={`${id}-title`} className="rounded-xl bg-surface-container-low p-4">
      <h2 id={`${id}-title`} className="flex items-center gap-2 text-title-m text-on-surface">
        <Icon name="document_search" className="size-5 text-on-surface-variant" />
        {copy.title}
      </h2>
      <p className="mt-0.5 text-body-m text-on-surface-variant">{copy.hint}</p>

      {perSource.map(({ source, index, flags: here }) => {
        if (source.kind === 'image') {
          const boxed = here
            .map((f) => ({ f, box: boxToPercent(f.flag.box_2d) }))
            .filter((b) => b.box !== null)
          return (
            <div key={index} className="mt-4 flex justify-center rounded-lg bg-surface-container-highest/60 p-3">
              <div className="relative inline-block max-w-full">
                <img
                  src={source.url}
                  alt={copy.imageAlt(source.name, boxed.length)}
                  className="block max-h-[460px] w-auto max-w-full rounded-md shadow-e1"
                />
                {boxed.map(({ f, box }) => (
                  <button
                    key={f.n}
                    type="button"
                    data-testid={`flag-box-${f.n}`}
                    aria-label={copy.boxLabel(f.n, title(f))}
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
                      'absolute rounded-[6px] border-[2.5px] shadow-[0_0_0_1.5px_rgb(255_255_255/0.9)] transition-[background-color,box-shadow] duration-200 focus-visible:outline-offset-1',
                      BORDER[verdict],
                      active === f.n ? 'bg-black/10 shadow-[0_0_0_1.5px_rgb(255_255_255/0.9),0_0_0_6px_rgb(0_0_0/0.18)]' : 'bg-transparent hover:bg-black/5',
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
              <figcaption className="mb-1.5 flex items-center gap-1.5 text-label-l text-on-surface-variant">
                <Icon name="sms" className="size-4" />
                {copy.pasted}
              </figcaption>
              <blockquote className="rounded-lg rounded-tl-xs bg-surface-container-lowest px-4 py-3 text-body-m leading-relaxed whitespace-pre-wrap shadow-e1">
                {highlightQuotes(source.text, here).map((seg, i) =>
                  seg.n ? (
                    <mark
                      key={i}
                      className={cn(
                        'rounded px-0.5 text-on-surface ring-1 ring-current/20 [box-decoration-break:clone]',
                        SOFT[verdict],
                        active === seg.n && 'ring-2 ring-ring',
                      )}
                    >
                      <Marker n={seg.n} verdict={verdict} className="mr-1 size-5 align-[-3px] text-[11px]" />
                      <span className="sr-only">
                        {copy.boxLabel(seg.n, title({ n: seg.n, flag: numbered[seg.n - 1].flag }))}:
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
            <p key={index} className="mt-4 flex min-h-14 items-center gap-3 rounded-lg bg-surface-container-lowest px-4 py-2.5 text-body-m">
              <Icon name="picture_as_pdf" className="size-6 text-error" />
              <span className="truncate font-medium">{source.name}</span>
              <span className="shrink-0 text-on-surface-variant">· {copy.pdf}</span>
            </p>
          )
        }
        return null
      })}

      <ol className="mt-4 flex flex-col gap-0.5">
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
                  'ripple flex w-full gap-3.5 rounded-xs p-4 text-left text-on-surface transition-colors duration-200 [li:first-child>&]:rounded-t-lg [li:last-child>&]:rounded-b-lg',
                  active === f.n ? SOFT[verdict] : 'bg-surface-container-lowest',
                )}
              >
                <Marker n={f.n} verdict={verdict} className="mt-0.5" />
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="flex flex-wrap items-center gap-x-2 text-title-s">
                    {title(f)}
                    {showSeverity && (
                      <span className="rounded-xs bg-surface-container-high px-1.5 py-px text-label-s font-medium tracking-wide text-on-surface-variant">
                        {f.flag.severity}
                      </span>
                    )}
                  </span>
                  {text && <span className="text-body-l leading-snug">{text}</span>}
                  {f.flag.quote && (
                    <span className="text-body-m break-words text-on-surface-variant italic">“{f.flag.quote}”</span>
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
