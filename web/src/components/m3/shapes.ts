import { useSyncExternalStore } from 'react'

// The Material 3 Expressive shape library (cookie, sunny, burst, clover…), drawn as polar curves
// r(θ) = 1 + a·cos(kθ) on a fixed number of points, so any two of them morph into each other
// (SMIL <animate> in the loading indicator).

const N = 120 // points per outline: smooth at 160 px, and the same for every shape (morphable)

function polar(lobes: number, depth: number, turn = 0): string {
  const pts: string[] = []
  for (let i = 0; i < N; i++) {
    const t = (i / N) * Math.PI * 2
    const r = 44 * (1 + depth * Math.cos(lobes * (t + turn))) / (1 + depth)
    pts.push(`${(50 + r * Math.cos(t)).toFixed(2)},${(50 + r * Math.sin(t)).toFixed(2)}`)
  }
  return `M${pts.join('L')}Z`
}

export const SHAPES = {
  circle: polar(1, 0),
  cookie4: polar(4, 0.1, Math.PI / 4),
  cookie6: polar(6, 0.08),
  cookie9: polar(9, 0.06),
  cookie12: polar(12, 0.045),
  sunny: polar(8, 0.07),
  burst: polar(10, 0.12),
  clover: polar(4, 0.24, Math.PI / 4),
  flower: polar(5, 0.14, -Math.PI / 2),
  pentagon: polar(5, 0.07, -Math.PI / 2),
} as const
export type ShapeName = keyof typeof SHAPES

export const MORPH: ShapeName[] = ['cookie9', 'pentagon', 'burst', 'cookie4', 'sunny', 'clover', 'cookie9']

function subscribeMotion(cb: () => void) {
  const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)')
  mq?.addEventListener('change', cb)
  return () => mq?.removeEventListener('change', cb)
}
export function useReducedMotion(): boolean {
  return useSyncExternalStore(
    subscribeMotion,
    () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false,
    () => false,
  )
}
