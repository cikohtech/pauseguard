import { useId, type ReactNode } from 'react'

import { MORPH, SHAPES, useReducedMotion, type ShapeName } from '@/components/m3/shapes'
import { cn } from '@/lib/utils'

export type { ShapeName } from '@/components/m3/shapes'

// Material 3 Expressive pieces: shapes (components/m3/shapes.ts) with content on them, the
// morphing loading indicator and the wavy progress bar.

/** An M3 Expressive shape (filled with currentColor) with optional content centred on it. */
export function Shape({
  shape,
  className,
  shapeClassName,
  spin = false,
  children,
}: {
  shape: ShapeName
  className?: string
  shapeClassName?: string
  /** Turn the outline slowly (the content stays upright). */
  spin?: boolean
  children?: ReactNode
}) {
  return (
    <span className={cn('relative inline-flex items-center justify-center', className)}>
      <svg viewBox="0 0 100 100" aria-hidden="true" className={cn('absolute inset-0 size-full', spin && 'spin-slow', shapeClassName)}>
        <path d={SHAPES[shape]} fill="currentColor" />
      </svg>
      {children && <span className="relative inline-flex items-center justify-center">{children}</span>}
    </span>
  )
}

/**
 * The M3 Expressive loading indicator (contained): a shape that morphs through the library while
 * it turns. With reduced motion it is a still shape. Decorative: pair it with a status text.
 */
export function LoadingIndicator({ className }: { className?: string }) {
  const still = useReducedMotion()
  return (
    <span
      aria-hidden="true"
      className={cn('inline-flex size-12 items-center justify-center rounded-full bg-primary-container text-primary', className)}
    >
      <svg viewBox="0 0 100 100" className="size-[79%]">
        <path d={SHAPES.cookie9} fill="currentColor">
          {!still && (
            <>
              <animate
                attributeName="d"
                dur="4.2s"
                repeatCount="indefinite"
                calcMode="spline"
                keyTimes={MORPH.map((_, i) => (i / (MORPH.length - 1)).toFixed(3)).join(';')}
                keySplines={MORPH.slice(1).map(() => '0.2 0 0 1').join(';')}
                values={MORPH.map((s) => SHAPES[s]).join(';')}
              />
              <animateTransform
                attributeName="transform"
                type="rotate"
                from="0 50 50"
                to="360 50 50"
                dur="2.4s"
                repeatCount="indefinite"
              />
            </>
          )}
        </path>
      </svg>
    </span>
  )
}

/** M3 Expressive wavy linear progress: the active part is a sine wave, the track is flat. */
export function WavyProgress({
  durationMs,
  className,
  label,
}: {
  /** Fills once over this time (a determinate countdown). */
  durationMs: number
  className?: string
  label?: string
}) {
  const still = useReducedMotion()
  const clip = useId()
  const wave = Array.from({ length: 41 }, (_, i) => `${i * 10},${(6 + 3 * Math.sin((i / 4) * Math.PI * 2)).toFixed(2)}`)
  return (
    <span className={cn('relative block h-3 w-full', className)} role={label ? 'progressbar' : undefined} aria-label={label}>
      <svg viewBox="0 0 400 12" preserveAspectRatio="none" aria-hidden="true" className="absolute inset-0 size-full overflow-visible">
        <defs>
          <clipPath id={clip}>
            <rect x="0" y="-2" height="16" width={still ? 400 : 0}>
              {!still && <animate attributeName="width" from="0" to="400" dur={`${durationMs}ms`} fill="freeze" />}
            </rect>
          </clipPath>
        </defs>
        <line x1="0" y1="6" x2="400" y2="6" stroke="var(--secondary-container)" strokeWidth="4" strokeLinecap="round" />
        <polyline
          points={wave.join(' ')}
          fill="none"
          stroke="currentColor"
          strokeWidth="4"
          strokeLinecap="round"
          strokeLinejoin="round"
          clipPath={`url(#${clip})`}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
    </span>
  )
}
