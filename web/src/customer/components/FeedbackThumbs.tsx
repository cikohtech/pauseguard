import { useState } from 'react'
import { useTranslation } from 'react-i18next'

import { Icon } from '@/components/icons/Icon'
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
      'ripple inline-flex size-12 items-center justify-center rounded-full transition-colors duration-200',
      helpful === value
        ? 'bg-primary text-on-primary'
        : 'border border-outline-variant text-on-surface-variant',
      helpful !== null && helpful !== value && 'opacity-[0.38]',
    )

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-3 gap-y-1 py-2 text-body-m text-on-surface-variant">
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
          <Icon name="thumb_up" fill={helpful === true} className="size-5" />
        </button>
        <button
          type="button"
          className={thumb(false)}
          aria-label={t('customer.feedback.no')}
          aria-pressed={helpful === false}
          disabled={helpful !== null && helpful !== false}
          onClick={() => send(false)}
        >
          <Icon name="thumb_down" fill={helpful === false} className="size-5" />
        </button>
      </div>
      <span role="status" className={cn(helpful === null && 'sr-only')}>
        {helpful !== null ? t('customer.feedback.thanks') : ''}
      </span>
    </div>
  )
}
