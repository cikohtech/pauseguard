import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { consoleApi, type AnalystAction, type CaseDetail } from '@/console/api'
import { shortcutFor } from '@/console/shortcuts'
import { Kbd } from '@/console/components/bits'
import { ACTION_KEY, ACTION_LABEL, DECIDED_LABEL, STATUS_LABEL, money } from '@/console/format'
import { Icon, Sparkle, type IconName } from '@/components/icons/Icon'
import { button } from '@/components/m3/styles'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

const ACTIONS: { action: AnalystAction; icon: IconName }[] = [
  { action: 'RELEASE', icon: 'check_circle' },
  { action: 'HOLD', icon: 'back_hand' },
  { action: 'ESCALATE', icon: 'flag' },
  { action: 'REPORT_SCAM', icon: 'report' },
]

export function ActionBar({ detail, onDecided }: { detail: CaseDetail; onDecided: () => void }) {
  const navigate = useNavigate()
  const id = useId()
  const [note, setNote] = useState('')
  const [pending, setPending] = useState<AnalystAction | null>(null)
  const [confirmRelease, setConfirmRelease] = useState(false)
  const c = detail.case
  const recommended = c.case_file?.recommended_action ?? null
  const busy = useRef(false)

  const decide = useCallback(
    async (action: AnalystAction, confirmed = false) => {
      if (busy.current) return
      // Releasing a held (RED) payment sends the money: ask once.
      if (action === 'RELEASE' && c.verdict === 'RED' && !confirmed) {
        setConfirmRelease(true)
        return
      }
      busy.current = true
      setPending(action)
      try {
        const res = await consoleApi.decide(c.case_id, action, note.trim() || null)
        setNote('')
        if (action === 'REPORT_SCAM') {
          toast.success(DECIDED_LABEL[action], {
            description: `${res.watchlist_added} ${res.watchlist_added === 1 ? 'entity' : 'entities'} added to the watchlist`,
            action: { label: 'View watchlist', onClick: () => navigate('/console/watchlist') },
          })
        } else {
          toast.success(DECIDED_LABEL[action], { description: `${c.customer_name} · ${money(c.amount)}` })
        }
        onDecided()
      } catch (err) {
        toast.error('The decision wasn’t saved', {
          description: err instanceof ApiError ? err.message : 'Please try again.',
        })
      } finally {
        busy.current = false
        setPending(null)
      }
    },
    [c, note, navigate, onDecided],
  )

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.defaultPrevented || e.repeat || confirmRelease) return
      if (document.querySelector('[role="dialog"]')) return // another dialog owns the keyboard
      const action = shortcutFor(e)
      if (!action) return
      e.preventDefault()
      void decide(action)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [decide, confirmRelease])

  return (
    <div className="border-t border-outline-variant/70 bg-surface-container-lowest px-3 py-3 sm:px-6">
      <div className="flex flex-col gap-2 @4xl:flex-row @4xl:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <label htmlFor={`${id}-note`} className="sr-only">
            Note for the audit log (optional)
          </label>
          <div className="flex h-12 w-full min-w-0 items-center gap-2 rounded-full bg-surface-container-high px-4 transition-shadow focus-within:shadow-[inset_0_0_0_2px_var(--primary)]">
            <Icon name="edit_note" className="size-5 text-on-surface-variant" />
            <input
              id={`${id}-note`}
              value={note}
              maxLength={1000}
              onChange={(e) => setNote(e.target.value)}
              onKeyDown={(e) => e.key === 'Escape' && (e.currentTarget as HTMLInputElement).blur()}
              placeholder="Add a note for the audit log (optional)"
              className="h-full w-full min-w-0 bg-transparent text-body-m text-on-surface placeholder:text-on-surface-variant focus-visible:outline-none"
            />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-2 @xl:flex @xl:flex-wrap" role="group" aria-label="Decide this case">
          {ACTIONS.map(({ action, icon }) => {
            const isRecommended = recommended === action
            return (
              <button
                key={action}
                type="button"
                onClick={() => void decide(action)}
                disabled={pending !== null}
                aria-keyshortcuts={ACTION_KEY[action].toUpperCase()}
                className={cn(
                  button(action === 'REPORT_SCAM' ? 'danger' : isRecommended ? 'tonal' : 'outlined', 'sm', 'min-h-12 gap-2 px-5'),
                  action !== 'REPORT_SCAM' && !isRecommended && 'text-on-surface',
                  isRecommended && action === 'REPORT_SCAM' && 'shadow-[0_0_0_2px_var(--surface-container-lowest),0_0_0_4px_var(--error)]',
                )}
              >
                {pending === action ? (
                  <Icon name="progress_activity" className="animate-spin" />
                ) : isRecommended ? (
                  <Sparkle className="!size-[18px]" />
                ) : (
                  <Icon name={icon} />
                )}
                {ACTION_LABEL[action]}
                <Kbd className="hidden @xl:inline-flex">{ACTION_KEY[action]}</Kbd>
                {isRecommended && <span className="sr-only"> (recommended)</span>}
              </button>
            )
          })}
        </div>
      </div>
      <p className="mt-2 hidden items-center gap-1.5 text-body-s text-on-surface-variant @xl:flex">
        <Icon name="keyboard" className="size-4" />
        Status: <span className="font-medium text-on-surface">{STATUS_LABEL[c.status]}</span>
        {c.assigned_to && c.status !== 'OPEN' && ` by ${c.assigned_to}`}
        {recommended && (
          <>
            {' '}
            · Recommended: <span className="font-medium text-on-surface">{ACTION_LABEL[recommended]}</span>
          </>
        )}
        <span> · Shortcuts work anywhere outside the note field.</span>
      </p>

      <Dialog open={confirmRelease} onOpenChange={setConfirmRelease}>
        <DialogContent>
          <DialogHeader>
            <Icon name="warning" className="size-6 text-error" />
            <DialogTitle>Release this held payment?</DialogTitle>
            <DialogDescription>
              PauseGuard held {money(c.amount)} from {c.customer_name} as a likely scam. Releasing sends the money.
              Only release after you have spoken to the customer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="mt-2 sm:flex-row-reverse sm:justify-start">
            <button type="button" autoFocus onClick={() => setConfirmRelease(false)} className={button('filled', 'sm')}>
              Keep it held
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirmRelease(false)
                void decide('RELEASE', true)
              }}
              className={button('text', 'sm')}
            >
              Release payment
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
