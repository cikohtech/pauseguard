import { initials } from '@/customer/format'
import { cn } from '@/lib/utils'

// Persona avatars: initials on a tonal container (M3 "fixed" accent colours, the same in every
// scope so a persona looks the same in the phone and on the stage). Synthetic people: no photos.
const TONE: Record<string, string> = {
  cust_001: 'bg-[#ACEDFF] text-[#004E5C]',
  cust_002: 'bg-[#DDE1FF] text-[#3F4565]',
  cust_003: 'bg-[#FFDCC2] text-[#6E3900]',
}
const SIZE = { sm: 'size-10 text-[15px]', md: 'size-12 text-[17px]', lg: 'size-14 text-[19px]' }

export function Avatar({ id, name, size = 'md', className }: { id: string; name: string; size?: keyof typeof SIZE; className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full font-medium',
        TONE[id] ?? 'bg-secondary-container text-on-secondary-container',
        SIZE[size],
        className,
      )}
    >
      {initials(name)}
    </span>
  )
}
