import type { WatchlistEntry, WatchlistType } from '@/console/api'
import { TYPOLOGY_LABEL, WATCHLIST_TYPE_LABEL } from '@/console/format'

/** Case-insensitive search over the value, type, source and typologies. */
export function filterWatchlist(entries: readonly WatchlistEntry[], query: string, type: WatchlistType | 'ALL') {
  const q = query.trim().toLowerCase()
  return entries.filter((e) => {
    if (type !== 'ALL' && e.type !== type) return false
    if (!q) return true
    const hay = [e.value, WATCHLIST_TYPE_LABEL[e.type], e.source === 'SEED' ? 'intel feed seed' : 'analyst report', ...e.typologies.map((t) => TYPOLOGY_LABEL[t])]
      .join(' ')
      .toLowerCase()
    // phone numbers and accounts are stored without spaces or dashes: match them the same way
    return hay.includes(q) || e.value.toLowerCase().includes(q.replace(/[\s-]/g, ''))
  })
}
