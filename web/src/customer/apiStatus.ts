// Is the live API answering? The app pings GET /personas when it opens. That also wakes a
// scaled-to-zero Cloud Run instance while the visitor picks a persona, so the first check
// doesn't pay the cold start. The desktop caption shows the result.
import { useSyncExternalStore } from 'react'

import { api } from '@/lib/api'
import { getIdToken } from '@/lib/firebase'

export type ApiStatus = 'checking' | 'ok' | 'down'

let status: ApiStatus = 'checking'
let started = false
const listeners = new Set<() => void>()

function set(next: ApiStatus) {
  status = next
  for (const l of listeners) l()
}

export function pingApi(tries = 5) {
  if (started) return
  started = true
  // Sign in (anonymously) early as well, so the first POST /checks has its token ready.
  getIdToken().catch(() => {})
  const attempt = (left: number) => {
    api
      .personas()
      .then(() => set('ok'))
      .catch(() => {
        set('down')
        if (left > 1) setTimeout(() => attempt(left - 1), 4000)
      })
  }
  attempt(tries)
}

export function useApiStatus(): ApiStatus {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    () => status,
    () => status,
  )
}
