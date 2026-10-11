import { Search } from 'lucide-react'
import { useEffect, useId, useMemo, useState } from 'react'

import { consoleApi, type WatchlistEntry, type WatchlistType } from '@/console/api'
import { TYPOLOGY_LABEL, WATCHLIST_TYPE_LABEL, ago } from '@/console/format'
import { filterWatchlist } from '@/console/watchlist'
import { useConsoleTitle } from '@/console/title'
import { useNow } from '@/console/useNow'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export const WATCHLIST_REFRESH_MS = 10_000
const NEW_MS = 15 * 60_000 // an analyst report from the last 15 minutes is marked "New"

// /console/watchlist (UI_SPEC Area 2, item 4): every phone, link and account the bank blocks.
// "Report as scam" adds to it; agents only read it.
export function Watchlist() {
  useConsoleTitle('Watchlist')
  const now = useNow()
  const id = useId()
  const [entries, setEntries] = useState<WatchlistEntry[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [query, setQuery] = useState('')
  const [type, setType] = useState<WatchlistType | 'ALL'>('ALL')

  useEffect(() => {
    let live = true
    const load = () =>
      consoleApi
        .watchlist()
        .then((e) => {
          if (!live) return
          setEntries(e)
          setFailed(false)
        })
        .catch(() => live && setFailed(true))
    void load()
    const timer = setInterval(() => void load(), WATCHLIST_REFRESH_MS)
    return () => {
      live = false
      clearInterval(timer)
    }
  }, [])

  const shown = useMemo(() => (entries ? filterWatchlist(entries, query, type) : []), [entries, query, type])
  const reported = entries?.filter((e) => e.source === 'ANALYST_REPORT').length ?? 0

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-[1280px] flex-col gap-4 px-4 py-5 sm:px-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Watchlist</h1>
          <p className="text-sm text-muted-foreground">
            Scam phones, links and accounts. Every check looks them up; “Report as scam” in a case adds to this list.
            {entries && (
              <>
                {' '}
                {entries.length} entries, {reported} from analyst reports.
              </>
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-0 flex-1 sm:max-w-sm">
            <label htmlFor={`${id}-q`} className="sr-only">
              Search the watchlist
            </label>
            <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              id={`${id}-q`}
              type="search"
              placeholder="Search a phone, domain, account or typology"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-9"
            />
          </div>
          <div role="group" aria-label="Entry type" className="inline-flex flex-wrap rounded-lg border border-border bg-card p-0.5">
            {(['ALL', 'PHONE', 'DOMAIN', 'URL', 'ACCOUNT'] as const).map((t) => (
              <button
                key={t}
                type="button"
                aria-pressed={type === t}
                onClick={() => setType(t)}
                className={cn(
                  'min-h-10 rounded-md px-3 text-sm font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                  type === t ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {t === 'ALL' ? 'All' : WATCHLIST_TYPE_LABEL[t]}
              </button>
            ))}
          </div>
        </div>

        {failed && (
          <p role="alert" className="rounded-lg bg-verdict-red-soft px-3 py-2 text-sm text-verdict-red-ink">
            The watchlist couldn’t be loaded. Retrying.
          </p>
        )}

        <div
          role="region"
          aria-label="Watchlist entries"
          tabIndex={0}
          className="overflow-x-auto rounded-xl border border-border bg-card outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <table className="w-full min-w-[720px] text-sm">
            <caption className="sr-only">
              Watchlist entries, most recently seen first{query && `, matching “${query}”`}
            </caption>
            <thead className="border-b border-border text-left text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="px-4 py-2.5 font-medium">Type</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Value</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Source</th>
                <th scope="col" className="px-4 py-2.5 text-right font-medium">Reports</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Typologies</th>
                <th scope="col" className="px-4 py-2.5 font-medium">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {entries === null && !failed
                ? [0, 1, 2, 3].map((i) => (
                    <tr key={i}>
                      <td colSpan={6} className="px-4 py-2">
                        <Skeleton className="h-6" />
                      </td>
                    </tr>
                  ))
                : shown.map((e) => {
                    const fresh = e.source === 'ANALYST_REPORT' && now.getTime() - new Date(e.last_seen).getTime() < NEW_MS
                    return (
                      <tr key={`${e.type}-${e.value}`} className={cn('border-t border-border first:border-t-0', fresh && 'bg-primary-soft/60')}>
                        <td className="px-4 py-2.5">{WATCHLIST_TYPE_LABEL[e.type]}</td>
                        <td className="px-4 py-2.5 font-mono text-[13px] break-all">
                          {e.value}
                          {fresh && (
                            <span className="ml-2 rounded-full bg-primary px-1.5 py-0.5 font-sans text-[11px] font-semibold text-primary-foreground">
                              New
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2.5">
                          {e.source === 'SEED' ? (
                            <span className="text-muted-foreground">Intel feed</span>
                          ) : (
                            <span className="font-medium">Analyst report</span>
                          )}
                        </td>
                        <td className="px-4 py-2.5 text-right font-semibold tabular-nums">{e.reported_count}</td>
                        <td className="px-4 py-2.5 text-muted-foreground">
                          {e.typologies.length ? e.typologies.map((t) => TYPOLOGY_LABEL[t]).join(', ') : '—'}
                        </td>
                        <td className="px-4 py-2.5 whitespace-nowrap text-muted-foreground">
                          <time dateTime={e.last_seen}>{ago(new Date(e.last_seen), now)}</time>
                        </td>
                      </tr>
                    )
                  })}
              {entries && shown.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">
                    Nothing matches “{query}”.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
