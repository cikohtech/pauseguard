// The live queue of OPEN cases (PRD A1). In cloud it is a Firestore realtime listener on `cases`
// (status == OPEN, newest first; the composite index is in infra/firestore.indexes.json), read
// with the analyst's own Firebase session under the rules' role=analyst check. Locally (no
// Firebase config) and if the listener fails, it polls GET /cases every second instead.
import type { Timestamp } from 'firebase/firestore'

import { consoleApi, type CaseSummary } from '@/console/api'
import { consoleFirebase } from '@/console/auth'
import type { Verdict } from '@/lib/api'

export interface QueueCase extends CaseSummary {
  createdAt: Date
}

export type FeedSource = 'firestore' | 'polling'

const VERDICT_RANK: Record<Verdict, number> = { RED: 0, AMBER: 1, GREEN: 2 }
export const POLL_MS = 1000
const MAX_CASES = 100

/** RED first, then AMBER, then newest first (UI_SPEC Area 2, queue). */
export function sortQueue(cases: readonly QueueCase[]): QueueCase[] {
  return [...cases].sort(
    (a, b) =>
      VERDICT_RANK[a.verdict] - VERDICT_RANK[b.verdict] ||
      b.createdAt.getTime() - a.createdAt.getTime() ||
      a.case_id.localeCompare(b.case_id),
  )
}

export function fromSummary(c: CaseSummary): QueueCase {
  return { ...c, createdAt: new Date(c.created_at) }
}

type CaseDoc = Omit<CaseSummary, 'title' | 'created_at'> & {
  created_at: Timestamp | Date | string
  case_file?: { title?: string } | null
}

/** A Firestore `cases` document (DATA_SPEC §3) as a queue row. */
export function fromDoc(id: string, doc: CaseDoc): QueueCase {
  const raw = doc.created_at
  const createdAt =
    raw instanceof Date
      ? raw
      : typeof raw === 'string'
        ? new Date(raw)
        : (raw as Timestamp).toDate()
  return {
    case_id: doc.case_id ?? id,
    check_id: doc.check_id,
    customer_name: doc.customer_name,
    customer_age: doc.customer_age ?? null,
    amount: doc.amount,
    verdict: doc.verdict,
    typology: doc.typology,
    confidence: doc.confidence,
    status: doc.status,
    title: doc.case_file?.title ?? null,
    created_at: createdAt.toISOString(),
    createdAt,
  }
}

export interface FeedHandlers {
  onData: (cases: QueueCase[], source: FeedSource) => void
  onError: (err: unknown) => void
}

function poll({ onData, onError }: FeedHandlers): () => void {
  let stopped = false
  let timer: ReturnType<typeof setTimeout> | undefined
  const tick = async () => {
    try {
      const cases = await consoleApi.openCases()
      if (!stopped) onData(sortQueue(cases.map(fromSummary)), 'polling')
    } catch (err) {
      if (!stopped) onError(err)
    }
    if (!stopped) timer = setTimeout(() => void tick(), POLL_MS)
  }
  void tick()
  return () => {
    stopped = true
    clearTimeout(timer)
  }
}

/** Starts the feed; returns the function that stops it. */
export function subscribeOpenCases(handlers: FeedHandlers): () => void {
  const pending = consoleFirebase()
  if (!pending) return poll(handlers)

  let stop = () => {}
  let stopped = false
  void (async () => {
    try {
      const [{ app }, fs] = await Promise.all([pending, import('firebase/firestore')])
      if (stopped) return
      const q = fs.query(
        fs.collection(fs.getFirestore(app), 'cases'),
        fs.where('status', '==', 'OPEN'),
        fs.orderBy('created_at', 'desc'),
        fs.limit(MAX_CASES),
      )
      stop = fs.onSnapshot(
        q,
        (snap) => {
          const rows = snap.docs.map((d) => fromDoc(d.id, d.data() as CaseDoc))
          handlers.onData(sortQueue(rows), 'firestore')
        },
        (err) => {
          // e.g. the index is still building after a fresh deploy: keep the queue alive.
          console.warn('Firestore listener failed; polling the API instead', err)
          if (!stopped) stop = poll(handlers)
        },
      )
    } catch (err) {
      console.warn('Firestore unavailable; polling the API instead', err)
      if (!stopped) stop = poll(handlers)
    }
  })()
  return () => {
    stopped = true
    stop()
  }
}
