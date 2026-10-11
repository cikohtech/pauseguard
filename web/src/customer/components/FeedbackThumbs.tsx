import { ThumbsDown, ThumbsUp } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { api } from '@/lib/api'
import { cn } from '@/lib/utils'

/** "Was this helpful? 👍 👎" under every verdict (POST /checks/{id}/feedback). */
export function FeedbackThumbs({ checkId }: { checkId: string }) {
  const { t } = useTranslation()
  const [helpful, setHelpful] = useState<boolean | null>(null)

  const send = (value: boolean) => {
    if (helpful !== null) return
    setHelpful(value)
    // best effort: feedback never blocks the customer
    api.feedback(checkId, value).catch(() => {})
  }

  const thumb = (value: boolean) =>
    cn(
      'inline-flex size-11 items-center justify-center rounded-full border outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50',
      helpful === value
        ? 'border-primary bg-primary text-primary-foreground'
        : 'border-input bg-card text-muted-foreground hover:bg-muted hover:text-foreground',
      helpful !== null && helpful !== value && 'opacity-50',
    )

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 py-2 text-sm text-muted-foreground">
      <span id={`fb-${checkId}`}>{t('customer.feedback.question')}</span>
      <div role="group" aria-labelledby={`fb-${checkId}`} className="flex gap-2">
        <button
          type="button"
          className={thumb(true)}
          aria-label={t('customer.feedback.yes')}
          aria-pressed={helpful === true}
          disabled={helpful !== null && helpful !== true}
          onClick={() => send(true)}
        >
          <ThumbsUp aria-hidden="true" className="size-5" />
        </button>
        <button
          type="button"
          className={thumb(false)}
          aria-label={t('customer.feedback.no')}
          aria-pressed={helpful === false}
          disabled={helpful !== null && helpful !== false}
          onClick={() => send(false)}
        >
          <ThumbsDown aria-hidden="true" className="size-5" />
        </button>
      </div>
      <span role="status" className={cn(helpful === null && 'sr-only')}>
        {helpful !== null ? t('customer.feedback.thanks') : ''}
      </span>
    </div>
  )
}
