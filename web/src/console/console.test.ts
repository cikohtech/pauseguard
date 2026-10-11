// Pure logic of the analyst console: queue order, arrivals, shortcuts, evidence mapping,
// watchlist search, history points and the audit trail.
import type { CaseHistory, WatchlistEntry } from '@/console/api'
import { auditEntries } from '@/console/audit'
import { analystFlags, entityChips, evidenceSources, matchesWatchlist } from '@/console/evidence'
import { fromDoc, sortQueue, type QueueCase } from '@/console/feed'
import { ago, compactMoney, money, uploadName } from '@/console/format'
import { historyPoints } from '@/console/history'
import { shortcutFor } from '@/console/shortcuts'
import { newArrivals } from '@/console/useQueue'
import { filterWatchlist } from '@/console/watchlist'
import { TAN_DETAIL } from '@/test/consoleFixtures'

const row = (id: string, verdict: QueueCase['verdict'], minutesAgo: number): QueueCase => {
  const createdAt = new Date(Date.UTC(2026, 9, 11, 6, 0) - minutesAgo * 60_000)
  return {
    case_id: id,
    check_id: `chk_${id}`,
    customer_name: id,
    customer_age: null,
    amount: 100,
    verdict,
    typology: 'UNKNOWN',
    confidence: 0.5,
    status: 'OPEN',
    title: null,
    created_at: createdAt.toISOString(),
    createdAt,
  }
}

test('the queue puts RED first, then AMBER, newest first within a verdict', () => {
  const sorted = sortQueue([row('a1', 'AMBER', 1), row('r_old', 'RED', 30), row('a2', 'AMBER', 5), row('r_new', 'RED', 2)])
  expect(sorted.map((c) => c.case_id)).toEqual(['r_new', 'r_old', 'a1', 'a2'])
})

test('a Firestore case document becomes a queue row (Timestamp, case-file title)', () => {
  const at = new Date('2026-10-11T06:00:00Z')
  const doc = {
    case_id: 'case_1',
    check_id: 'chk_1',
    customer_id: 'cust_001',
    customer_name: 'Tan Mei Ling',
    customer_age: 67,
    amount: 8000,
    verdict: 'RED' as const,
    typology: 'GOV_OFFICIAL_IMPERSONATION' as const,
    confidence: 0.99,
    status: 'OPEN' as const,
    created_at: { toDate: () => at } as never,
    case_file: { title: 'MAS impersonation, S$8,000' },
  }
  const c = fromDoc('case_1', doc)
  expect(c.createdAt).toEqual(at)
  expect(c.created_at).toBe('2026-10-11T06:00:00.000Z')
  expect(c.title).toBe('MAS impersonation, S$8,000')
  expect(fromDoc('case_2', { ...doc, case_id: undefined as never, case_file: null }).case_id).toBe('case_2')
})

test('only cases after the first load count as new arrivals', () => {
  const first = [row('a', 'RED', 1)]
  expect(newArrivals(null, first)).toEqual([])
  const next = [...first, row('b', 'AMBER', 0)]
  expect(newArrivals(new Set(['a']), next).map((c) => c.case_id)).toEqual(['b'])
})

test('shortcuts R/H/E/S fire outside text fields and without modifiers only', () => {
  const key = (k: string, target: Partial<HTMLElement> = { tagName: 'BODY' }, mods = {}) =>
    shortcutFor({ key: k, altKey: false, ctrlKey: false, metaKey: false, target: target as EventTarget, ...mods })
  expect(key('r')).toBe('RELEASE')
  expect(key('H')).toBe('HOLD')
  expect(key('e')).toBe('ESCALATE')
  expect(key('s')).toBe('REPORT_SCAM')
  expect(key('x')).toBeNull()
  expect(key('s', { tagName: 'INPUT' })).toBeNull()
  expect(key('s', { tagName: 'TEXTAREA' })).toBeNull()
  expect(key('s', { tagName: 'DIV', isContentEditable: true })).toBeNull()
  expect(key('s', undefined, { metaKey: true })).toBeNull() // Cmd+S is the browser's
  expect(key('r', undefined, { ctrlKey: true })).toBeNull()
})

test('evidence sources follow the upload order, then the pasted text', () => {
  const sources = evidenceSources(TAN_DETAIL)
  expect(sources).toEqual([
    { kind: 'image', name: 'chat.png', url: 'https://storage.example/chat.png?sig=1' },
    { kind: 'pdf', name: 'letter.pdf' }, // no signed link: keeps its slot
    { kind: 'text', text: 'Officer Lee: transfer to the safe account today' },
  ])
  expect(uploadName('gs://b/checks/chk_1/12-my-chat.png')).toBe('my-chat.png')
})

test('the analyst sees the top flags first, then the rest, without duplicates', () => {
  const codes = analystFlags(TAN_DETAIL).map((f) => f.code)
  expect(codes).toEqual(['SAFE_ACCOUNT', 'WATCHLIST_MATCH', 'AUTHORITY_CLAIM', 'URGENCY'])
})

test('entity chips include the payee account and mark watchlist hits', () => {
  const chips = entityChips(TAN_DETAIL)
  expect(chips.map((c) => [c.kind, c.value, c.onWatchlist])).toEqual([
    ['PHONE', '+65 8000 0147', true],
    ['URL', 'https://mas-gov-verify.example/case/2231', true],
    ['ACCOUNT', '123-45678-9', false],
    ['ORG', 'MAS', false],
  ])
  expect(chips[2].payee).toBe(true)
  const m = [{ type: 'PHONE' as const, value: '+6580000147', source: 'SEED' as const, reported_count: 1 }]
  expect(matchesWatchlist('PHONE', '8000 0147', m)).toBe(true) // local format, same number
  expect(matchesWatchlist('PHONE', '8000 0148', m)).toBe(false)
  expect(matchesWatchlist('ORG', 'MAS', m)).toBe(false)
})

const entry = (value: string, type: WatchlistEntry['type'], source: WatchlistEntry['source'] = 'SEED'): WatchlistEntry => ({
  type,
  value,
  source,
  reported_count: 1,
  first_seen: '2026-10-01T00:00:00Z',
  last_seen: '2026-10-11T00:00:00Z',
  typologies: type === 'DOMAIN' ? ['GOV_OFFICIAL_IMPERSONATION'] : [],
})

test('watchlist search matches values typed with spaces, types and typologies', () => {
  const list = [entry('+6580000147', 'PHONE'), entry('mas-gov-verify.example', 'DOMAIN', 'ANALYST_REPORT'), entry('123456789', 'ACCOUNT')]
  expect(filterWatchlist(list, '8000 0147', 'ALL').map((e) => e.type)).toEqual(['PHONE'])
  expect(filterWatchlist(list, '123-456', 'ALL').map((e) => e.type)).toEqual(['ACCOUNT'])
  expect(filterWatchlist(list, 'government', 'ALL').map((e) => e.type)).toEqual(['DOMAIN'])
  expect(filterWatchlist(list, 'analyst', 'ALL')).toHaveLength(1)
  expect(filterWatchlist(list, '', 'ACCOUNT')).toHaveLength(1)
  expect(filterWatchlist(list, '', 'ALL')).toHaveLength(3)
})

test('the 90-day chart ends with this transfer as its own highlighted bar', () => {
  const h: CaseHistory = {
    customer_id: 'cust_001',
    as_of: '2026-10-11T06:00:00Z',
    days: [
      { day: '2026-10-10', amount: 120.5, count: 2 },
      { day: '2026-10-11', amount: 0, count: 0 },
    ],
    median_debit_90d: 60,
    transfer_amount: 8000,
  }
  const pts = historyPoints(h)
  expect(pts.map((p) => [p.label, p.amount, p.isTransfer, p.valueLabel])).toEqual([
    ['10 Oct', 120.5, false, ''],
    ['11 Oct', 0, false, ''],
    ['This transfer', 8000, true, 'S$8,000'],
  ])
})

test('the audit trail runs from the check-in to the analyst actions', () => {
  const items = auditEntries(TAN_DETAIL)
  expect(items.map((i) => i.what)).toEqual([
    'Asked the customer a check-in question',
    'Answered and shared 3 pieces of evidence',
    'RED verdict; case opened',
    'Hold',
    'Added to the watchlist',
  ])
  expect(items[3].who).toBe('analyst@harbourbank.example')
  expect(items[3].note).toBe('Called the customer')
})

test('money and time formats', () => {
  expect(money(8000)).toBe('S$8,000')
  expect(money(450.5)).toBe('S$450.50')
  expect(compactMoney(8450)).toBe('S$8,450')
  expect(compactMoney(184_500)).toBe('S$184.5K')
  const now = new Date('2026-10-11T06:00:00Z')
  expect(ago(new Date('2026-10-11T05:59:40Z'), now)).toBe('just now')
  expect(ago(new Date('2026-10-11T05:57:00Z'), now)).toBe('3 min ago')
  expect(ago(new Date('2026-10-11T03:00:00Z'), now)).toBe('3 h ago')
  expect(ago(new Date('2026-10-04T03:00:00Z'), now)).toBe('4 Oct')
})
