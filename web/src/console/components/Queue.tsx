import { Link } from 'react-router-dom'

import { TypologyChip, VerdictBadge } from '@/console/components/bits'
import type { QueueCase } from '@/console/feed'
import { VERDICT_ICON, ago, money } from '@/console/format'
import type { QueueState } from '@/console/useQueue'
import { useNow } from '@/console/useNow'
import { Icon } from '@/components/icons/Icon'
import { iconButton } from '@/components/m3/styles'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

// The realtime queue (UI_SPEC Area 2, item 1): OPEN cases, RED first, then newest. A case that
// arrives while the console is open slides in with a highlight and is announced to screen readers.

const AVATAR = {
  RED: 'bg-verdict-red-soft text-verdict-red-ink',
  AMBER: 'bg-verdict-amber-soft text-verdict-amber-ink',
  GREEN: 'bg-verdict-green-soft text-verdict-green-ink',
} as const

export function Queue({
  queue,
  selectedId,
  sound,
  onToggleSound,
}: {
  queue: QueueState
  selectedId: string | null
  sound: boolean
  onToggleSound: () => void
}) {
  const now = useNow()
  const { cases, source, failing, fresh } = queue
  const counts = { RED: 0, AMBER: 0, GREEN: 0 }
  for (const c of cases ?? []) counts[c.verdict] += 1

  return (
    <section aria-labelledby="queue-title" className="flex h-full min-h-0 flex-col">
      <div className="flex items-start gap-2 px-5 pt-5 pb-3">
        <div className="min-w-0 flex-1">
          <h1 id="queue-title" className="flex items-center gap-2 text-title-l">
            Open cases
            {cases && (
              <span className="inline-flex h-6 min-w-6 items-center justify-center rounded-full bg-primary px-2 text-label-m font-medium text-on-primary tabular-nums">
                {cases.length}
              </span>
            )}
          </h1>
          <p className="mt-1 flex items-center gap-1.5 text-body-s text-on-surface-variant">
            <LiveDot source={source} failing={failing} />
          </p>
          {cases && cases.length > 0 && (
            <p className="mt-2 flex gap-1.5">
              <span className="inline-flex h-6 items-center gap-1 rounded-sm bg-verdict-red-soft px-2 text-label-m font-medium text-verdict-red-ink">
                <Icon name="gpp_bad" fill className="size-3.5" />
                {counts.RED} RED
              </span>
              <span className="inline-flex h-6 items-center gap-1 rounded-sm bg-verdict-amber-soft px-2 text-label-m font-medium text-verdict-amber-ink">
                <Icon name="warning" fill className="size-3.5" />
                {counts.AMBER} AMBER
              </span>
            </p>
          )}
        </div>
        <button type="button" onClick={onToggleSound} aria-pressed={sound} title={sound ? 'Sound on' : 'Sound off'} className={iconButton('standard', '-mr-2')}>
          <Icon name={sound ? 'notifications_active' : 'notifications_off'} fill={sound} />
          <span className="sr-only">Sound for new cases</span>
        </button>
      </div>

      <div aria-live="polite" className="sr-only">
        {queue.announcement}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {cases === null ? (
          failing ? (
            <p role="alert" className="mx-3 flex gap-2 rounded-lg bg-error-container p-4 text-body-m text-on-error-container">
              <Icon name="error" className="size-5" />
              The queue can’t be loaded right now. It will retry by itself.
            </p>
          ) : (
            <div className="flex flex-col gap-1 px-3" aria-busy="true" aria-label="Loading cases">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-[84px] rounded-xl" />
              ))}
            </div>
          )
        ) : cases.length === 0 ? (
          <EmptyQueue />
        ) : (
          <ul className="flex flex-col gap-0.5 px-3 pb-3" aria-label="Open cases, RED first">
            {cases.map((c) => (
              <QueueRow key={c.case_id} c={c} selected={c.case_id === selectedId} fresh={fresh.has(c.case_id)} now={now} />
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

function LiveDot({ source, failing }: { source: QueueState['source']; failing: boolean }) {
  if (failing) {
    return (
      <>
        <span aria-hidden="true" className="size-2 rounded-full bg-verdict-amber" />
        Reconnecting…
      </>
    )
  }
  if (!source) return <span>Connecting…</span>
  return (
    <>
      <span aria-hidden="true" className="relative flex size-2">
        <span className="absolute inline-flex size-full animate-ping rounded-full bg-verdict-green opacity-60 motion-reduce:hidden" />
        <span className="relative inline-flex size-2 rounded-full bg-verdict-green" />
      </span>
      {source === 'firestore' ? 'Live · Firestore' : 'Live · polling'}
    </>
  )
}

function QueueRow({ c, selected, fresh, now }: { c: QueueCase; selected: boolean; fresh: boolean; now: Date }) {
  return (
    <li data-case-id={c.case_id} data-verdict={c.verdict} className={cn(fresh && 'queue-row-in')}>
      <Link
        to={`/console/cases/${c.case_id}`}
        aria-current={selected ? 'true' : undefined}
        className={cn(
          'ripple focus-inset flex items-start gap-3 rounded-xl px-3 py-3 transition-colors duration-200',
          selected ? 'bg-secondary-container text-on-secondary-container' : 'text-on-surface',
          fresh && !selected && 'queue-row-fresh',
        )}
      >
        {/* the verdict icon as the row's avatar (an svg: no text, so the row reads "RED · name …") */}
        <span aria-hidden="true" className={cn('mt-0.5 inline-flex size-10 shrink-0 items-center justify-center rounded-full', AVATAR[c.verdict])}>
          <Icon name={VERDICT_ICON[c.verdict]} fill className="size-5" />
        </span>
        <span className="flex min-w-0 flex-1 flex-col gap-1">
          <span className="flex items-center gap-2">
            {/* the verdict word, first for screen readers; the chip below shows it */}
            <span className="sr-only">{c.verdict}</span>
            <span className="min-w-0 flex-1 truncate text-title-s">
              {c.customer_name}
              {c.customer_age !== null && <span className="font-normal text-on-surface-variant">, {c.customer_age}</span>}
            </span>
            <span className="text-title-s tabular-nums">{money(c.amount)}</span>
          </span>
          <span className="flex items-center gap-1.5 text-body-s text-on-surface-variant">
            <span aria-hidden="true" className="contents">
              <VerdictBadge verdict={c.verdict} />
            </span>
            <TypologyChip typology={c.typology} className="min-w-0" />
            {fresh && (
              <span className="inline-flex h-5 items-center rounded-full bg-primary px-2 text-label-s font-medium text-on-primary">New</span>
            )}
            <time dateTime={c.created_at} className="ml-auto shrink-0">
              {ago(c.createdAt, now)}
            </time>
          </span>
        </span>
      </Link>
    </li>
  )
}

function EmptyQueue() {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span className="inline-flex size-16 items-center justify-center rounded-full bg-surface-container text-on-surface-variant">
        <Icon name="inbox" className="size-8" />
      </span>
      <p className="text-title-m">No open cases</p>
      <p className="text-body-m text-on-surface-variant">
        RED and AMBER checks appear here the moment the customer sees their verdict.
      </p>
      <a href="/app" target="_blank" rel="noreferrer" className="ripple inline-flex min-h-10 items-center gap-1.5 rounded-full px-4 text-label-l font-medium text-primary">
        Make one in the customer app
        <Icon name="open_in_new" className="size-4" />
        <span className="sr-only">(opens in a new tab)</span>
      </a>
    </div>
  )
}
