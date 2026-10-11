import { useCallback, useEffect, useRef, useState } from 'react'

import { consoleApi, type CaseDetail } from '@/console/api'
import { ApiError } from '@/lib/api'

export const CASEFILE_POLL_MS = 2000
const CASEFILE_POLL_MAX = 20 // the case-file agent's budget is 25 s (CASEFILE_TIMEOUT_SECONDS)

export type CaseLoad =
  | { status: 'loading' }
  | { status: 'error'; notFound: boolean }
  | { status: 'ready'; detail: CaseDetail }

/**
 * One case (GET /cases/{id}). The case exists from the customer's verdict, but its case file is
 * written a few seconds later, so while `case_file` is null the case is fetched again every 2 s.
 */
export function useCase(caseId: string | null): { load: CaseLoad; reload: () => Promise<void> } {
  const [load, setLoad] = useState<CaseLoad>({ status: 'loading' })
  const current = useRef(caseId)

  const fetchCase = useCallback(async (id: string) => {
    const detail = await consoleApi.getCase(id)
    if (current.current === id) setLoad({ status: 'ready', detail })
    return detail
  }, [])

  useEffect(() => {
    current.current = caseId
    if (!caseId) return
    let stopped = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const run = async (attempt: number) => {
      try {
        const detail = await fetchCase(caseId)
        if (!stopped && !detail.case.case_file && attempt < CASEFILE_POLL_MAX) {
          timer = setTimeout(() => void run(attempt + 1), CASEFILE_POLL_MS)
        }
      } catch (err) {
        if (stopped) return
        const notFound = err instanceof ApiError && err.status === 404
        setLoad((l) => (l.status === 'ready' ? l : { status: 'error', notFound }))
      }
    }
    void run(0)
    return () => {
      stopped = true
      clearTimeout(timer)
    }
  }, [caseId, fetchCase])

  const reload = useCallback(async () => {
    if (caseId) await fetchCase(caseId).catch(() => {})
  }, [caseId, fetchCase])

  return { load, reload }
}
