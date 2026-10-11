import { Bell, BellOff, ExternalLink, Inbox } from 'lucide-react'
import { Link } from 'react-router-dom'

import { TypologyChip, VerdictBadge } from '@/console/components/bits'
import type { QueueCase } from '@/console/feed'
import { ago, money } from '@/console/format'
import type { QueueState } from '@/console/useQueue'
import { useNow } from '@/console/useNow'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

// The realtime queue (UI_SPEC Area 2, item 1): OPEN cases, RED first, then newest. A case that
// arrives while the console is open slides in with a highlight and is announced to screen readers.

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
      <div className="flex items-center gap-2 border-b border-border px-4 py-3">
        <div className="min-w-0 flex-1">
          <h1 id="queue-title" className="flex items-center gap-2 text-base font-semibold">
            Open cases
            {cases && (
              <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-semibold tabular-nums">
                {cases.length}
              </span>
            )}
          </h1>
          <p className="mt-0.5 flex items-center gap-1.5 text-xs text-muted-foreground">
            <LiveDot source={source} failing={failing} />
            {cases && cases.length > 0 && (
              <span>
                · {counts.RED} RED · {counts.AMBER} AMBER
              </span>
            )}
          </p>
        </div>
        <button
          type="button"
          onClick={onToggleSound}
          aria-pressed={sound}
          className="inline-flex size-11 items-center justify-center rounded-lg text-muted-foreground outline-none hover:bg-muted hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          {sound ? <Bell aria-hidden="true" className="size-5" /> : <BellOff aria-hidden="true" className="size-5" />}
          <span className="sr-only">Sound for new cases</span>
        </button>
      </div>

      <div aria-live="polite" className="sr-only">
        {queue.announcement}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {cases === null ? (
          failing ? (
            <p role="alert" className="p-4 text-sm text-verdict-red-ink">
              The queue can’t be loaded right now. It will retry by itself.
            </p>
          ) : (
            <div className="flex flex-col gap-2 p-3" aria-busy="true" aria-label="Loading cases">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-[76px] rounded-xl" />
              ))}
            </div>
          )
        ) : cases.length === 0 ? (
          <EmptyQueue />
        ) : (
          <ul className="flex flex-col gap-1.5 p-2" aria-label="Open cases, RED first">
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
          'group relative flex flex-col gap-1.5 rounded-xl border px-3 py-2.5 outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50',
          selected
            ? 'border-primary/40 bg-primary-soft'
            : 'border-transparent hover:border-border hover:bg-card',
          fresh && !selected && 'queue-row-fresh',
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            'absolute inset-y-2 left-0 w-1 rounded-r-full',
            c.verdict === 'RED' ? 'bg-verdict-red' : c.verdict === 'AMBER' ? 'bg-verdict-amber' : 'bg-verdict-green',
          )}
        />
        <span className="flex items-center gap-2">
          <VerdictBadge verdict={c.verdict} />
          <span className="min-w-0 flex-1 truncate font-medium">
            {c.customer_name}
            {c.customer_age !== null && <span className="font-normal text-muted-foreground">, {c.customer_age}</span>}
          </span>
          <span className="font-semibold tabular-nums">{money(c.amount)}</span>
        </span>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          <TypologyChip typology={c.typology} className="min-w-0" />
          {fresh && <span className="font-semibold text-primary">New</span>}
          <time dateTime={c.created_at} className="ml-auto shrink-0">
            {ago(c.createdAt, now)}
          </time>
        </span>
      </Link>
    </li>
  )
}

function EmptyQueue() {
  return (
    <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
      <span className="inline-flex size-12 items-center justify-center rounded-2xl bg-muted text-muted-foreground">
        <Inbox aria-hidden="true" className="size-6" />
      </span>
      <p className="font-medium">No open cases</p>
      <p className="text-sm text-muted-foreground">
        RED and AMBER checks appear here the moment the customer sees their verdict.
      </p>
      <a
        href="/app"
        target="_blank"
        rel="noreferrer"
        className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 text-sm font-medium text-primary underline underline-offset-4 outline-none hover:text-brand-deep focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        Make one in the customer app
        <ExternalLink aria-hidden="true" className="size-4" />
        <span className="sr-only">(opens in a new tab)</span>
      </a>
    </div>
  )
}
