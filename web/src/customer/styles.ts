// The phone screens' action buttons: M3 pills, 56px tall and full width (44px+ tap targets,
// UI_SPEC accessibility; large for older customers). The quiet variant is an M3 text button.
import { button } from '@/components/m3/styles'
import { cn } from '@/lib/utils'

export function bigButton(variant: 'primary' | 'tonal' | 'outline' | 'quiet' | 'danger' = 'primary') {
  if (variant === 'quiet') return button('text', 'md', 'w-full whitespace-normal')
  const v = { primary: 'filled', tonal: 'tonal', outline: 'outlined', danger: 'danger' } as const
  return cn(button(v[variant], 'lg', 'w-full whitespace-normal'))
}
