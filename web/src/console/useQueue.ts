import { useEffect, useRef, useState } from 'react'

import { chime } from '@/console/chime'
import { subscribeOpenCases, type FeedSource, type QueueCase } from '@/console/feed'

export const FRESH_MS = 8000

/** Cases in `cases` that weren't in `known`. The first load (known = null) adds nothing new. */
export function newArrivals(known: ReadonlySet<string> | null, cases: readonly QueueCase[]): QueueCase[] {
  if (!known) return []
  return cases.filter((c) => !known.has(c.case_id))
}

export interface QueueState {
  cases: QueueCase[] | null // null until the first answer
  source: FeedSource | null
  failing: boolean
  fresh: ReadonlySet<string> // arrived in the last FRESH_MS: highlighted
  announcement: string // for the aria-live region
}

/** The live queue, plus which cases just arrived (highlight, announcement, optional chime). */
export function useQueue(sound: boolean): QueueState {
  const [state, setState] = useState<QueueState>({
    cases: null,
    source: null,
    failing: false,
    fresh: new Set(),
    announcement: '',
  })
  const known = useRef<Set<string> | null>(null)
  const soundRef = useRef(sound)
  useEffect(() => {
    soundRef.current = sound
  }, [sound])

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = []
    const stop = subscribeOpenCases({
      onData: (cases, source) => {
        const added = newArrivals(known.current, cases)
        known.current = new Set([...(known.current ?? []), ...cases.map((c) => c.case_id)])
        setState((s) => {
          const fresh = new Set(s.fresh)
          for (const c of added) fresh.add(c.case_id)
          const first = added[0]
          return {
            cases,
            source,
            failing: false,
            fresh,
            announcement: first
              ? `New ${first.verdict} case: ${first.customer_name}, S$${first.amount.toLocaleString('en-SG')}`
              : s.announcement,
          }
        })
        if (added.length > 0) {
          if (soundRef.current) chime()
          timers.push(
            setTimeout(() => {
              setState((s) => {
                const fresh = new Set(s.fresh)
                for (const c of added) fresh.delete(c.case_id)
                return { ...s, fresh }
              })
            }, FRESH_MS),
          )
        }
      },
      onError: () => setState((s) => ({ ...s, failing: true })),
    })
    return () => {
      stop()
      timers.forEach(clearTimeout)
    }
  }, [])

  return state
}
