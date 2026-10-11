import { useEffect } from 'react'

import { PRODUCT_NAME } from '@/lib/product'

/** Sets the tab title for a console page ("Queue · PauseGuard console"). */
export function useConsoleTitle(page: string) {
  useEffect(() => {
    const previous = document.title
    document.title = `${page} · ${PRODUCT_NAME} console`
    return () => {
      document.title = previous
    }
  }, [page])
}
