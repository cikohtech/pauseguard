import { ShieldCheck } from 'lucide-react'

import { PRODUCT_NAME } from '@/lib/product'

export function ShieldMark() {
  return (
    <span className="inline-flex items-center gap-2 font-semibold text-primary">
      <ShieldCheck aria-hidden="true" className="size-6" />
      {PRODUCT_NAME}
    </span>
  )
}
