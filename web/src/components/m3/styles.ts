// Material 3 component classes, shared by the customer app (Harbour Bank scheme) and the console
// (Google scheme): the colours come from the scope's role tokens (index.css), so one class string
// looks right in both. Every pressable surface carries a state layer and a ripple (.ripple).
import { cn } from '@/lib/utils'

export type ButtonVariant = 'filled' | 'tonal' | 'outlined' | 'text' | 'elevated' | 'danger' | 'danger-tonal'
export type ButtonSize = 'sm' | 'md' | 'lg'

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  filled: 'bg-primary text-on-primary hover:shadow-e1',
  tonal: 'bg-secondary-container text-on-secondary-container hover:shadow-e1',
  outlined: 'border border-outline text-primary',
  text: 'text-primary',
  elevated: 'bg-surface-container-low text-primary shadow-e1 hover:shadow-e2',
  danger: 'bg-error text-on-error hover:shadow-e1',
  'danger-tonal': 'bg-error-container text-on-error-container',
}
const BUTTON_SIZE: Record<ButtonSize, string> = {
  sm: 'min-h-10 gap-2 px-4 text-label-l font-medium [&_svg]:size-[18px]',
  md: 'min-h-12 gap-2 px-6 text-[15px] font-medium [&_svg]:size-5',
  lg: 'min-h-14 gap-2.5 px-7 text-title-m font-medium [&_svg]:size-6',
}

/** M3 common button: filled, tonal, outlined, text or elevated; a full-radius pill. */
export function button(variant: ButtonVariant = 'filled', size: ButtonSize = 'md', className?: string) {
  return cn(
    'ripple inline-flex shrink-0 items-center justify-center rounded-full text-center whitespace-nowrap select-none transition-[box-shadow,background-color] duration-200 ease-standard disabled:pointer-events-none disabled:opacity-[0.38] [&_svg]:shrink-0',
    BUTTON_VARIANT[variant],
    BUTTON_SIZE[size],
    variant === 'text' && (size === 'sm' ? 'px-3' : 'px-4'),
    className,
  )
}

/** M3 icon button (standard by default): 48px target, 24px icon. */
export function iconButton(variant: 'standard' | 'filled' | 'tonal' | 'outlined' = 'standard', className?: string) {
  return cn(
    'ripple inline-flex size-12 shrink-0 items-center justify-center rounded-full transition-colors disabled:pointer-events-none disabled:opacity-[0.38] [&_svg]:size-6',
    variant === 'standard' && 'text-on-surface-variant',
    variant === 'filled' && 'bg-primary text-on-primary',
    variant === 'tonal' && 'bg-secondary-container text-on-secondary-container',
    variant === 'outlined' && 'border border-outline-variant text-on-surface-variant',
    className,
  )
}

/** M3 chip (assist / filter / suggestion): 32px tall (padded to a 44px+ target by the caller if needed). */
export function chip(selected = false, className?: string) {
  return cn(
    'ripple inline-flex min-h-8 items-center gap-2 rounded-sm px-4 text-label-l font-medium transition-colors [&_svg]:size-[18px] [&_svg]:shrink-0',
    selected
      ? 'bg-secondary-container text-on-secondary-container'
      : 'border border-outline-variant bg-transparent text-on-surface-variant',
    className,
  )
}

/** M3 outlined text field (the input itself; pair with a floating <label>, see TextField). */
export const fieldBase =
  'peer block w-full rounded-xs border border-outline bg-transparent px-4 text-body-l text-on-surface caret-primary transition-[border-color,box-shadow] duration-150 placeholder:text-on-surface-variant/70 hover:border-on-surface focus:border-primary focus:shadow-[inset_0_0_0_1px_var(--primary)] focus-visible:outline-none aria-invalid:border-error aria-invalid:focus:shadow-[inset_0_0_0_1px_var(--error)]'

/** M3 card. */
export function card(variant: 'filled' | 'outlined' | 'elevated' = 'outlined', className?: string) {
  return cn(
    'rounded-md',
    variant === 'filled' && 'bg-surface-container-highest/60',
    variant === 'outlined' && 'border border-outline-variant bg-surface-container-lowest',
    variant === 'elevated' && 'bg-surface-container-low shadow-e1',
    className,
  )
}
