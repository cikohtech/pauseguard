import { PRODUCT_NAME } from '@/lib/product'
import { cn } from '@/lib/utils'

/** The PauseGuard mark: a shield with a pause sign, in the scope's primary colour. */
export function PauseGuardLogo({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" aria-hidden="true" focusable="false" className={cn('size-7 shrink-0', className)}>
      <path
        d="M16 2.5 4.5 6.8v8.4c0 7.3 4.9 12.4 11.5 14.3 6.6-1.9 11.5-7 11.5-14.3V6.8L16 2.5Z"
        className="fill-primary"
      />
      <path d="M16 2.5v27c6.6-1.9 11.5-7 11.5-14.3V6.8L16 2.5Z" fill="#000" opacity="0.14" />
      <rect x="11.2" y="10.5" width="3.4" height="10" rx="1.7" fill="#fff" />
      <rect x="17.4" y="10.5" width="3.4" height="10" rx="1.7" fill="#fff" />
    </svg>
  )
}

export function ShieldMark({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-2 text-[20px] leading-none font-medium tracking-[-0.01em] text-on-surface', className)}>
      <PauseGuardLogo />
      {PRODUCT_NAME}
    </span>
  )
}
