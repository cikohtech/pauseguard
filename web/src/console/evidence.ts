// Pure helpers for the case view's Evidence tab.
import type { CaseDetail, WatchlistMatch, WatchlistType } from '@/console/api'
import { uploadName } from '@/console/format'
import type { EvidenceSource } from '@/customer/evidence'
import type { RedFlag } from '@/lib/api'

/** The customer's answer (the last customer message), with its uploads and pasted text. */
export function customerAnswer(detail: CaseDetail) {
  return [...detail.messages].reverse().find((m) => m.role === 'customer') ?? null
}

/**
 * The evidence in the order the agents saw it (uploads, then the pasted text), so that a flag's
 * `evidence_index` points at the right item. An upload whose read URL couldn't be signed stays
 * in its slot as a named file, so later indexes don't shift.
 */
export function evidenceSources(detail: CaseDetail): EvidenceSource[] {
  const answer = customerAnswer(detail)
  if (!answer) return []
  const sources: EvidenceSource[] = answer.evidence_uris.map((uri, index) => {
    const name = uploadName(uri)
    const link = detail.evidence_links.find((l) => l.index === index)
    if (link && link.content_type.startsWith('image/')) return { kind: 'image', name, url: link.url }
    return { kind: 'pdf', name }
  })
  if (answer.pasted_text) sources.push({ kind: 'text', text: answer.pasted_text })
  return sources
}

const flagKey = (f: RedFlag) => `${f.code}|${f.quote}`

/** Every flag the analyst should see: the policy's top flags first, then the rest the evidence agent found. */
export function analystFlags(detail: CaseDetail): RedFlag[] {
  const top = detail.fusion?.top_flags ?? []
  const seen = new Set(top.map(flagKey))
  const rest = (detail.evidence?.red_flags ?? []).filter((f) => !seen.has(flagKey(f)))
  return [...top, ...rest]
}

export type EntityKind = 'PHONE' | 'URL' | 'ACCOUNT' | 'ORG' | 'APP'

export interface EntityChip {
  kind: EntityKind
  value: string
  onWatchlist: boolean
  payee?: boolean
}

const alnum = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, '')
const host = (url: string) =>
  url
    .toLowerCase()
    .replace(/^[a-z]+:\/\//, '')
    .replace(/^www\./, '')
    .split(/[/?#]/)[0]

/** Loose match against the watchlist hits (they are stored normalised: E.164, bare digits, hosts). */
export function matchesWatchlist(kind: EntityKind, value: string, matches: readonly WatchlistMatch[]): boolean {
  const types: Partial<Record<EntityKind, WatchlistType[]>> = {
    PHONE: ['PHONE'],
    ACCOUNT: ['ACCOUNT'],
    URL: ['URL', 'DOMAIN'],
  }
  const wanted = types[kind]
  if (!wanted) return false
  return matches.some((m) => {
    if (!wanted.includes(m.type)) return false
    if (kind === 'URL') return m.type === 'DOMAIN' ? host(value) === m.value : alnum(value) === alnum(m.value)
    const a = alnum(value)
    const b = alnum(m.value)
    return a === b || (kind === 'PHONE' && (a.endsWith(b) || b.endsWith(a)) && Math.min(a.length, b.length) >= 8)
  })
}

/** Phones, links, accounts, organisations and apps the evidence agent extracted, plus the payee account. */
export function entityChips(detail: CaseDetail): EntityChip[] {
  const e = detail.evidence?.entities
  const matches = detail.intel?.watchlist_matches ?? []
  const out: EntityChip[] = []
  const add = (kind: EntityKind, value: string, payee = false) => {
    if (!value.trim() || out.some((c) => c.kind === kind && alnum(c.value) === alnum(value))) return
    out.push({ kind, value, onWatchlist: matchesWatchlist(kind, value, matches), ...(payee && { payee }) })
  }
  for (const v of e?.phones ?? []) add('PHONE', v)
  for (const v of e?.urls ?? []) add('URL', v)
  add('ACCOUNT', detail.transfer.account_number, true)
  for (const v of e?.accounts ?? []) add('ACCOUNT', v)
  for (const v of e?.orgs ?? []) add('ORG', v)
  for (const v of e?.apps ?? []) add('APP', v)
  return out
}
