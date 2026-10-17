import { useEffect, useId, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { consoleApi, type WatchlistEntry, type WatchlistType } from '@/console/api'
import { TYPOLOGY_LABEL, WATCHLIST_TYPE_LABEL, ago } from '@/console/format'
import { filterWatchlist } from '@/console/watchlist'
import { useConsoleTitle } from '@/console/title'
import { useNow } from '@/console/useNow'
import { Icon, type IconName } from '@/components/icons/Icon'
import { chip } from '@/components/m3/styles'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'

export const WATCHLIST_REFRESH_MS = 10_000
const NEW_MS = 15 * 60_000 // an analyst report from the last 15 minutes is marked "New"
const TYPE_ICON: Record<WatchlistType, IconName> = { PHONE: 'call', URL: 'link', DOMAIN: 'language', ACCOUNT: 'credit_card' }

// /console/watchlist (UI_SPEC Area 2, item 4): every phone, link and account the bank blocks.
// "Report as scam" adds to it; agents only read it.
export function Watchlist() {
  useConsoleTitle('Watchlist')
  const now = useNow()
  const id = useId()
  const [entries, setEntries] = useState<WatchlistEntry[] | null>(null)
  const [failed, setFailed] = useState(false)
  // the console's header search lands here with ?q=; a new search replaces what was typed
  const [params] = useSearchParams()
  const q = params.get('q') ?? ''
  const [query, setQuery] = useState(q)
  const [lastQ, setLastQ] = useState(q)
  if (q !== lastQ) {
    setLastQ(q)
    setQuery(q)
  }
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
      <div className="mx-auto flex max-w-[1320px] flex-col gap-4 px-4 py-6 sm:px-8">
        <div>
          <h1 className="text-headline-s text-on-surface">Watchlist</h1>
          <p className="mt-1 text-body-m text-on-surface-variant">
            Scam phones, links and accounts. Every check looks them up; “Report as scam” in a case adds to this list.
            {entries && (
              <>
                {' '}
                {entries.length} entries, {reported} from analyst reports.
              </>
            )}
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div className="relative min-w-0 flex-1 sm:max-w-md">
            <label htmlFor={`${id}-q`} className="sr-only">
              Search the watchlist
            </label>
            <Icon name="search" className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-on-surface-variant" />
            <input
              id={`${id}-q`}
              type="search"
              placeholder="Search a phone, domain, account or typology"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="h-12 w-full rounded-full bg-surface-container-high pr-4 pl-12 text-body-l text-on-surface placeholder:text-on-surface-variant focus-visible:outline-offset-0"
            />
          </div>
          <div role="group" aria-label="Entry type" className="flex flex-wrap gap-2">
            {(['ALL', 'PHONE', 'DOMAIN', 'URL', 'ACCOUNT'] as const).map((t) => {
              const on = type === t
              return (
                <button key={t} type="button" aria-pressed={on} onClick={() => setType(t)} className={chip(on, 'min-h-10 rounded-md')}>
                  {on ? <Icon name="check" /> : t !== 'ALL' && <Icon name={TYPE_ICON[t]} />}
                  {t === 'ALL' ? 'All' : WATCHLIST_TYPE_LABEL[t]}
                </button>
              )
            })}
          </div>
        </div>

        {failed && (
          <p role="alert" className="flex items-center gap-2 rounded-lg bg-error-container px-4 py-3 text-body-m text-on-error-container">
            <Icon name="error" className="size-5" />
            The watchlist couldn’t be loaded. Retrying.
          </p>
        )}

        <div
          role="region"
          aria-label="Watchlist entries"
          tabIndex={0}
          className="overflow-x-auto rounded-xl border border-outline-variant/80 bg-surface-container-lowest"
        >
          <table className="w-full min-w-[760px] text-body-m">
            <caption className="sr-only">
              Watchlist entries, most recently seen first{query && `, matching “${query}”`}
            </caption>
            <thead className="border-b border-outline-variant/70 bg-surface-container-low text-left text-label-l text-on-surface-variant">
              <tr>
                <th scope="col" className="h-12 px-5 font-medium">Type</th>
                <th scope="col" className="h-12 px-5 font-medium">Value</th>
                <th scope="col" className="h-12 px-5 font-medium">Source</th>
                <th scope="col" className="h-12 px-5 text-right font-medium">Reports</th>
                <th scope="col" className="h-12 px-5 font-medium">Typologies</th>
                <th scope="col" className="h-12 px-5 font-medium">Last seen</th>
              </tr>
            </thead>
            <tbody>
              {entries === null && !failed
                ? [0, 1, 2, 3].map((i) => (
                    <tr key={i}>
                      <td colSpan={6} className="px-5 py-2">
                        <Skeleton className="h-8" />
                      </td>
                    </tr>
                  ))
                : shown.map((e) => {
                    const fresh = e.source === 'ANALYST_REPORT' && now.getTime() - new Date(e.last_seen).getTime() < NEW_MS
                    return (
                      <tr
                        key={`${e.type}-${e.value}`}
                        className={cn(
                          'border-t border-outline-variant/50 transition-colors first:border-t-0 hover:bg-surface-container-low',
                          fresh && 'bg-primary-container/40',
                        )}
                      >
                        <td className="h-14 px-5">
                          <span className="inline-flex items-center gap-2.5">
                            <span className="inline-flex size-8 items-center justify-center rounded-full bg-surface-container-high text-on-surface-variant">
                              <Icon name={TYPE_ICON[e.type]} className="size-[18px]" />
                            </span>
                            {WATCHLIST_TYPE_LABEL[e.type]}
                          </span>
                        </td>
                        <td className="h-14 px-5 font-mono text-[13px] break-all text-on-surface">
                          {e.value}
                          {fresh && (
                            <span className="ml-2 inline-flex h-5 items-center rounded-full bg-primary px-2 font-sans text-label-s font-medium text-on-primary">
                              New
                            </span>
                          )}
                        </td>
                        <td className="h-14 px-5">
                          {e.source === 'SEED' ? (
                            <span className="inline-flex h-6 items-center gap-1 rounded-sm border border-outline-variant px-2 text-label-m font-medium text-on-surface-variant">
                              <Icon name="database" className="size-3.5" />
                              Intel feed
                            </span>
                          ) : (
                            <span className="inline-flex h-6 items-center gap-1 rounded-sm bg-secondary-container px-2 text-label-m font-medium text-on-secondary-container">
                              <Icon name="shield_person" className="size-3.5" />
                              Analyst report
                            </span>
                          )}
                        </td>
                        <td className="h-14 px-5 text-right text-title-s tabular-nums">{e.reported_count}</td>
                        <td className="h-14 px-5 text-on-surface-variant">
                          {e.typologies.length ? e.typologies.map((t) => TYPOLOGY_LABEL[t]).join(', ') : '—'}
                        </td>
                        <td className="h-14 px-5 whitespace-nowrap text-on-surface-variant">
                          <time dateTime={e.last_seen}>{ago(new Date(e.last_seen), now)}</time>
                        </td>
                      </tr>
                    )
                  })}
              {entries && shown.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-5 py-12 text-center text-body-m text-on-surface-variant">
                    <Icon name="search" className="mx-auto mb-2 size-8 opacity-60" />
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
