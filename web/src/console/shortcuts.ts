import type { AnalystAction } from '@/console/api'
import { ACTION_KEY } from '@/console/format'

const BY_KEY = Object.fromEntries(Object.entries(ACTION_KEY).map(([a, k]) => [k, a])) as Record<string, AnalystAction>

/**
 * The analyst action for a key press, or null. Shortcuts are single letters (R/H/E/S) and never
 * fire while the analyst is typing (the note field, any input) or with a modifier held.
 */
export function shortcutFor(e: Pick<KeyboardEvent, 'key' | 'altKey' | 'ctrlKey' | 'metaKey' | 'target'>): AnalystAction | null {
  if (e.altKey || e.ctrlKey || e.metaKey) return null
  const el = e.target as HTMLElement | null
  if (el && (el.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName))) return null
  return BY_KEY[e.key.toLowerCase()] ?? null
}
