import { use, useId, type SVGProps } from 'react'

import { IconSetContext } from '@/components/icons/context'
import type { IconName } from '@/components/icons/names'
import { cn } from '@/lib/utils'

export type { IconName } from '@/components/icons/names'

// Material Symbols as inline SVG (scripts/gen-icons.mjs), in the style the area's IconSetContext
// gives (components/icons/context.ts).

export function Icon({
  name,
  fill = false,
  className,
  ...props
}: { name: IconName; fill?: boolean } & Omit<SVGProps<SVGSVGElement>, 'name' | 'fill'>) {
  const set = use(IconSetContext)
  const d = (fill && set[`${name}-fill`]) || set[name]
  return (
    <svg
      viewBox="0 -960 960 960"
      fill="currentColor"
      aria-hidden="true"
      focusable="false"
      className={cn('size-6 shrink-0', className)}
      {...props}
    >
      <path d={d} />
    </svg>
  )
}

/**
 * The four-point "AI" sparkle in a blue → violet → rose gradient: marks what Gemini wrote or
 * found, the way Google products label AI output. Decorative; the text beside it says "Gemini".
 */
export function Sparkle({ className }: { className?: string }) {
  const id = useId()
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false" className={cn('size-5 shrink-0', className)}>
      <defs>
        <linearGradient id={id} x1="2" y1="22" x2="22" y2="2" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#1A73E8" />
          <stop offset="0.55" stopColor="#8E5CD9" />
          <stop offset="1" stopColor="#D9576E" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${id})`}
        d="M12 1.5c.5 5.6 4.9 10 10.5 10.5-5.6.5-10 4.9-10.5 10.5C11.5 16.9 7.1 12.5 1.5 12 7.1 11.5 11.5 7.1 12 1.5Z"
      />
    </svg>
  )
}
