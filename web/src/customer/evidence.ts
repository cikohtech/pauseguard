// Pure helpers for the evidence card: where to draw each flag on the customer's own evidence.
import type { CustomerMessage, RedFlag } from '@/lib/api'

export interface BoxPercent {
  top: number
  left: number
  width: number
  height: number
}

const clamp = (n: number) => Math.min(1000, Math.max(0, n))

/**
 * Gemini's `box_2d` is [ymin, xmin, ymax, xmax] normalised to 0-1000 on the image. As CSS
 * percentages of the image box it stays correct at any rendered size. Returns null for a box
 * that can't be drawn (wrong length, not numbers, or no area after clamping).
 */
export function boxToPercent(box: readonly number[] | null | undefined): BoxPercent | null {
  if (!box || box.length !== 4 || box.some((n) => typeof n !== 'number' || !Number.isFinite(n))) {
    return null
  }
  const [ymin, xmin, ymax, xmax] = box.map(clamp)
  if (ymax <= ymin || xmax <= xmin) return null
  return {
    top: ymin / 10,
    left: xmin / 10,
    width: (xmax - xmin) / 10,
    height: (ymax - ymin) / 10,
  }
}

/** One piece of evidence the customer shared, in the order the API saw it. */
export type EvidenceSource =
  | { kind: 'image'; name: string; url: string }
  | { kind: 'pdf'; name: string }
  | { kind: 'text'; text: string }

/** A flag as numbered on screen (1-based, in the order of `top_flags`). */
export interface NumberedFlag {
  n: number
  flag: RedFlag
}

/**
 * Groups the numbered flags by the evidence item they point at. `evidence_index` follows the
 * API's order: uploads first, then the pasted text (orchestrator.analyse).
 */
export function flagsBySource(flags: readonly RedFlag[], sources: readonly EvidenceSource[]) {
  const numbered: NumberedFlag[] = flags.map((flag, i) => ({ n: i + 1, flag }))
  const perSource = sources.map((source, index) => ({
    source,
    index,
    flags: numbered.filter((f) => f.flag.evidence_index === index),
  }))
  return { numbered, perSource }
}

export interface TextSegment {
  text: string
  n?: number // the flag number when this segment is a quoted part
}

const fold = (s: string) => s.toLowerCase()

/**
 * Finds `quote` in `text`, ignoring case and runs of whitespace. Returns [start, end) offsets
 * into the original text, or null.
 */
export function findQuote(text: string, quote: string): [number, number] | null {
  const words = quote.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return null
  const escaped = words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'))
  const match = new RegExp(escaped.join('\\s+'), 'i').exec(text)
  if (match) return [match.index, match.index + match[0].length]
  // Quotes are sometimes trimmed or lightly paraphrased at the ends: try the longest head.
  const folded = fold(text)
  for (let len = Math.min(quote.length, 60); len >= 12; len -= 4) {
    const head = fold(quote.trim().slice(0, len))
    const at = folded.indexOf(head)
    if (at >= 0) return [at, at + head.length]
  }
  return null
}

/** Splits pasted text into plain and highlighted segments. Overlapping quotes keep the first. */
export function highlightQuotes(text: string, flags: readonly NumberedFlag[]): TextSegment[] {
  const spans = flags
    .map(({ n, flag }) => {
      const at = findQuote(text, flag.quote)
      return at ? { n, start: at[0], end: at[1] } : null
    })
    .filter((s): s is { n: number; start: number; end: number } => s !== null)
    .sort((a, b) => a.start - b.start || a.n - b.n)

  const segments: TextSegment[] = []
  let pos = 0
  for (const span of spans) {
    if (span.start < pos) continue // overlaps an earlier highlight
    if (span.start > pos) segments.push({ text: text.slice(pos, span.start) })
    segments.push({ text: text.slice(span.start, span.end), n: span.n })
    pos = span.end
  }
  if (pos < text.length) segments.push({ text: text.slice(pos) })
  return segments
}

/** The reviewed explanation for top flag `index` (same order as the flags, matched by code). */
export function explanationFor(
  message: CustomerMessage | null,
  flag: RedFlag,
  index: number,
): string | null {
  const list = message?.flag_explanations ?? []
  // one explanation per top flag, in the same order (explainer_agent.postprocess)
  if (list[index]?.code === flag.code) return list[index].text
  return list.find((e) => e.code === flag.code)?.text ?? null
}
