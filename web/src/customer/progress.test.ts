import { advanceByTime, applyEvent, initialProgress, type Progress } from '@/customer/progress'
import type { ProgressEvent } from '@/lib/api'

const ev = (type: ProgressEvent['type'], stage: ProgressEvent['stage'] = null): ProgressEvent => ({
  type,
  stage,
  data: null,
})

// The order the orchestrator emits (API_SPEC "GET /checks/{id}/events").
const ORDER: ProgressEvent[] = [
  ev('status', 'ANALYSING_EVIDENCE'),
  ev('status', 'CHECKING_INTEL'),
  ev('partial', 'ANALYSING_EVIDENCE'),
  ev('partial', 'CHECKING_INTEL'),
  ev('status', 'DECIDING'),
  ev('partial', 'DECIDING'),
  ev('status', 'WRITING'),
  ev('done', 'DONE'),
]

test('the step ticks follow the orchestrator events', () => {
  const seen: Progress[] = []
  ORDER.reduce((p, e) => {
    const next = applyEvent(p, e)
    seen.push(next)
    return next
  }, initialProgress())

  expect(seen[2]).toMatchObject({ reading: 'done', payee: 'active', compare: 'waiting' })
  expect(seen[3]).toMatchObject({ reading: 'done', payee: 'done', compare: 'waiting' })
  expect(seen[4]).toMatchObject({ compare: 'active', explain: 'waiting' })
  expect(seen[5]).toMatchObject({ compare: 'done', explain: 'waiting' })
  expect(seen[6]).toMatchObject({ explain: 'active' })
  expect(seen[7]).toEqual({ reading: 'done', payee: 'done', compare: 'done', explain: 'done' })
})

test('replayed events never move a step backwards', () => {
  const done = ORDER.slice(0, 6).reduce(applyEvent, initialProgress())
  const replayed = ORDER.slice(0, 6).reduce(applyEvent, done)
  expect(replayed).toEqual(done)
})

test('a partial DECIDING alone (late subscriber) completes the first three steps', () => {
  expect(applyEvent(initialProgress(), ev('partial', 'DECIDING'))).toEqual({
    reading: 'done',
    payee: 'done',
    compare: 'done',
    explain: 'waiting',
  })
})

test('without SSE the timer advances the ticks but never finishes the last one', () => {
  const p = advanceByTime(initialProgress(), 60_000)
  expect(p).toEqual({ reading: 'done', payee: 'done', compare: 'done', explain: 'active' })
  expect(advanceByTime(initialProgress(), 500)).toEqual(initialProgress())
})
