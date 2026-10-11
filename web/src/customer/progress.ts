// The analysing screen's step ticks, driven by the SSE progress events (API_SPEC "events").
// Order from the orchestrator: status ANALYSING_EVIDENCE, status CHECKING_INTEL,
// partial ANALYSING_EVIDENCE, partial CHECKING_INTEL, status DECIDING, partial DECIDING,
// status WRITING, done.
import type { ProgressEvent } from '@/lib/api'

export const STEPS = ['reading', 'payee', 'compare', 'explain'] as const
export type Step = (typeof STEPS)[number]
export type StepState = 'waiting' | 'active' | 'done'
export type Progress = Record<Step, StepState>

export const initialProgress = (): Progress => ({
  reading: 'active',
  payee: 'active',
  compare: 'waiting',
  explain: 'waiting',
})

const set = (p: Progress, step: Step, state: StepState): Progress =>
  // never move a step backwards (events are replayed when the stream reconnects)
  p[step] === 'done' || (p[step] === 'active' && state === 'waiting') ? p : { ...p, [step]: state }

export function applyEvent(p: Progress, ev: ProgressEvent): Progress {
  if (ev.type === 'done') return allDone()
  if (ev.type === 'partial') {
    if (ev.stage === 'ANALYSING_EVIDENCE') return set(p, 'reading', 'done')
    if (ev.stage === 'CHECKING_INTEL') return set(p, 'payee', 'done')
    if (ev.stage === 'DECIDING') {
      return set(set(set(p, 'reading', 'done'), 'payee', 'done'), 'compare', 'done')
    }
    return p
  }
  if (ev.type === 'status') {
    if (ev.stage === 'DECIDING') return set(p, 'compare', 'active')
    if (ev.stage === 'WRITING') {
      const q = set(set(set(p, 'reading', 'done'), 'payee', 'done'), 'compare', 'done')
      return set(q, 'explain', 'active')
    }
  }
  return p
}

export const allDone = (): Progress => ({
  reading: 'done',
  payee: 'done',
  compare: 'done',
  explain: 'done',
})

/**
 * Without SSE (blocked by a proxy, or an old browser) the ticks advance on a timer instead and
 * stop before the last step; the POST response then completes them.
 */
export function advanceByTime(p: Progress, elapsedMs: number): Progress {
  let q = p
  if (elapsedMs > 1800) q = set(set(q, 'reading', 'done'), 'compare', 'active')
  if (elapsedMs > 2800) q = set(q, 'payee', 'done')
  if (elapsedMs > 4500) q = set(set(q, 'compare', 'done'), 'explain', 'active')
  return q
}
