// Shared class names for the phone screens' buttons (44px+ tap targets, UI_SPEC accessibility).
import { cn } from '@/lib/utils'

/** A full-width action button, at least 48px tall (quiet: a text button, 44px). */
export function bigButton(variant: 'primary' | 'outline' | 'quiet' = 'primary') {
  return cn(
    'inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-xl px-4 text-[16px] font-semibold outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:size-5 [&_svg]:shrink-0',
    variant === 'primary' && 'bg-primary text-primary-foreground hover:bg-brand-deep',
    variant === 'outline' && 'border border-input bg-card text-foreground hover:bg-muted',
    variant === 'quiet' && 'min-h-11 text-[15px] font-medium text-muted-foreground underline underline-offset-4 hover:text-foreground',
  )
}
