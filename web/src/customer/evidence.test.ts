import {
  boxToPercent,
  explanationFor,
  findQuote,
  flagsBySource,
  highlightQuotes,
  type EvidenceSource,
} from '@/customer/evidence'
import type { CustomerMessage, RedFlag } from '@/lib/api'

const flag = (over: Partial<RedFlag>): RedFlag => ({
  code: 'URGENCY',
  severity: 'HIGH',
  quote: '',
  evidence_index: null,
  box_2d: null,
  ...over,
})

describe('boxToPercent', () => {
  test('converts [ymin, xmin, ymax, xmax] on 0-1000 into CSS percentages', () => {
    expect(boxToPercent([410, 60, 470, 940])).toEqual({ top: 41, left: 6, width: 88, height: 6 })
  })

  test('the full image is 0/0/100/100', () => {
    expect(boxToPercent([0, 0, 1000, 1000])).toEqual({ top: 0, left: 0, width: 100, height: 100 })
  })

  test('keeps fractions (no rounding drift on small boxes)', () => {
    expect(boxToPercent([125, 333, 130, 667])).toEqual({ top: 12.5, left: 33.3, width: 33.4, height: 0.5 })
  })

  test('clamps coordinates that overshoot the 0-1000 range', () => {
    expect(boxToPercent([-20, 900, 50, 1080])).toEqual({ top: 0, left: 90, width: 10, height: 5 })
  })

  test.each([
    ['null', null],
    ['three numbers', [1, 2, 3]],
    ['five numbers', [1, 2, 3, 4, 5]],
    ['inverted y', [500, 100, 400, 200]],
    ['inverted x', [100, 500, 200, 400]],
    ['zero height', [300, 100, 300, 200]],
    ['NaN', [Number.NaN, 0, 10, 10]],
    ['no area after clamping', [1100, 0, 1200, 100]],
  ])('returns null for an undrawable box: %s', (_, box) => {
    expect(boxToPercent(box as number[] | null)).toBeNull()
  })
})

describe('flagsBySource', () => {
  test('numbers flags 1..n in top_flags order and groups them by evidence_index', () => {
    const sources: EvidenceSource[] = [
      { kind: 'image', name: 'chat.png', url: 'blob:1' },
      { kind: 'text', text: 'pasted' },
    ]
    const flags = [
      flag({ code: 'SAFE_ACCOUNT', evidence_index: 0 }),
      flag({ code: 'WATCHLIST_MATCH' }), // from the watchlist: no evidence item
      flag({ code: 'URGENCY', evidence_index: 1 }),
      flag({ code: 'AUTHORITY_CLAIM', evidence_index: 0 }),
    ]
    const { numbered, perSource } = flagsBySource(flags, sources)
    expect(numbered.map((f) => f.n)).toEqual([1, 2, 3, 4])
    expect(perSource[0].flags.map((f) => f.n)).toEqual([1, 4])
    expect(perSource[1].flags.map((f) => f.n)).toEqual([3])
  })
})

describe('findQuote / highlightQuotes', () => {
  const chat =
    'Hi Raj! To unlock it, top up S$450 to your task wallet.\nGold slots are limited today, many members are waiting.'

  test('finds a quote ignoring case and whitespace differences', () => {
    const at = findQuote(chat, 'to UNLOCK it,   top up S$450')
    expect(at).not.toBeNull()
    expect(chat.slice(...at!)).toBe('To unlock it, top up S$450')
  })

  test('finds a Chinese quote (no spaces)', () => {
    const zh = '我们相信您是无辜的。您必须马上把钱转到金管局的安全账户。'
    expect(zh.slice(...findQuote(zh, '安全账户')!)).toBe('安全账户')
  })

  test('falls back to the head of a quote whose ending was paraphrased', () => {
    const at = findQuote(chat, 'Gold slots are limited today, hurry up now')
    expect(at).not.toBeNull()
    expect(chat.slice(...at!)).toMatch(/^Gold slots are limited/)
  })

  test('returns null for text that is not there', () => {
    expect(findQuote(chat, 'guaranteed 30% returns every month')).toBeNull()
    expect(findQuote(chat, '   ')).toBeNull()
  })

  test('splits the text into plain and numbered segments, in text order', () => {
    const segs = highlightQuotes(chat, [
      { n: 1, flag: flag({ quote: 'Gold slots are limited today' }) },
      { n: 2, flag: flag({ quote: 'top up S$450 to your task wallet' }) },
    ])
    expect(segs.map((s) => s.n ?? 0)).toEqual([0, 2, 0, 1, 0])
    expect(segs.map((s) => s.text).join('')).toBe(chat) // nothing lost or duplicated
  })

  test('an overlapping second quote is not highlighted twice', () => {
    const segs = highlightQuotes(chat, [
      { n: 1, flag: flag({ quote: 'top up S$450 to your task wallet' }) },
      { n: 2, flag: flag({ quote: 'S$450 to your task' }) },
    ])
    expect(segs.filter((s) => s.n).map((s) => s.n)).toEqual([1])
    expect(segs.map((s) => s.text).join('')).toBe(chat)
  })
})

describe('explanationFor', () => {
  const message: CustomerMessage = {
    language: 'en',
    headline: 'h',
    body: 'b',
    flag_explanations: [
      { code: 'SAFE_ACCOUNT', text: 'No safe accounts.' },
      { code: 'URGENCY', text: 'They rush you.' },
    ],
    next_steps: [],
  }

  test('matches by position, then by code', () => {
    expect(explanationFor(message, flag({ code: 'SAFE_ACCOUNT' }), 0)).toBe('No safe accounts.')
    expect(explanationFor(message, flag({ code: 'URGENCY' }), 0)).toBe('They rush you.')
    expect(explanationFor(message, flag({ code: 'PAY_TO_EARN' }), 1)).toBeNull()
    expect(explanationFor(null, flag({}), 0)).toBeNull()
  })
})
