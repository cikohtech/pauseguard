import { CircleCheck, Flag, Hand, Loader2, ShieldX, TriangleAlert } from 'lucide-react'
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'

import { consoleApi, type AnalystAction, type CaseDetail } from '@/console/api'
import { shortcutFor } from '@/console/shortcuts'
import { Kbd } from '@/console/components/bits'
import { ACTION_KEY, ACTION_LABEL, DECIDED_LABEL, STATUS_LABEL, money } from '@/console/format'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { ApiError } from '@/lib/api'
import { cn } from '@/lib/utils'

const ACTIONS: { action: AnalystAction; icon: typeof Hand; tone: string }[] = [
  { action: 'RELEASE', icon: CircleCheck, tone: 'border-input bg-card hover:bg-muted' },
  { action: 'HOLD', icon: Hand, tone: 'border-input bg-card hover:bg-muted' },
  { action: 'ESCALATE', icon: Flag, tone: 'border-input bg-card hover:bg-muted' },
  {
    action: 'REPORT_SCAM',
    icon: ShieldX,
    tone: 'border-transparent bg-verdict-red-ink text-white hover:bg-[color-mix(in_oklch,var(--verdict-red-ink),black_12%)]',
  },
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
    <div className="border-t border-border bg-card/95 px-3 py-2.5 shadow-[0_-4px_16px_rgba(15,27,36,0.06)] backdrop-blur sm:px-6">
      <div className="flex flex-col gap-2 xl:flex-row xl:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <label htmlFor={`${id}-note`} className="sr-only">
            Note for the audit log (optional)
          </label>
          <input
            id={`${id}-note`}
            value={note}
            maxLength={1000}
            onChange={(e) => setNote(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && (e.currentTarget as HTMLInputElement).blur()}
            placeholder="Add a note for the audit log (optional)"
            className="min-h-11 w-full min-w-0 rounded-lg border border-input bg-background px-3 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          />
        </div>
        <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap" role="group" aria-label="Decide this case">
          {ACTIONS.map(({ action, icon: Icon, tone }) => (
            <button
              key={action}
              type="button"
              onClick={() => void decide(action)}
              disabled={pending !== null}
              aria-keyshortcuts={ACTION_KEY[action].toUpperCase()}
              className={cn(
                'relative inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border px-3.5 text-sm font-semibold outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-60',
                tone,
                recommended === action && action !== 'REPORT_SCAM' && 'border-primary ring-1 ring-primary',
              )}
            >
              {pending === action ? (
                <Loader2 aria-hidden="true" className="size-4 animate-spin" />
              ) : (
                <Icon aria-hidden="true" className="size-4" />
              )}
              {ACTION_LABEL[action]}
              <Kbd className="hidden sm:inline-flex">{ACTION_KEY[action]}</Kbd>
              {recommended === action && <span className="sr-only"> (recommended)</span>}
            </button>
          ))}
        </div>
      </div>
      <p className="mt-1.5 hidden text-xs text-muted-foreground sm:block">
        Status: <span className="font-medium text-foreground">{STATUS_LABEL[c.status]}</span>
        {c.assigned_to && c.status !== 'OPEN' && ` by ${c.assigned_to}`}
        {recommended && (
          <>
            {' '}
            · Recommended: <span className="font-medium text-foreground">{ACTION_LABEL[recommended]}</span>
          </>
        )}
        <span> · Shortcuts work anywhere outside the note field.</span>
      </p>

      <Dialog open={confirmRelease} onOpenChange={setConfirmRelease}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <TriangleAlert aria-hidden="true" className="size-5 text-verdict-red" />
              Release this held payment?
            </DialogTitle>
            <DialogDescription>
              PauseGuard held {money(c.amount)} from {c.customer_name} as a likely scam. Releasing sends the money.
              Only release after you have spoken to the customer.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter className="sm:flex-row-reverse">
            <button
              type="button"
              autoFocus
              onClick={() => setConfirmRelease(false)}
              className="inline-flex min-h-11 items-center justify-center rounded-lg bg-primary px-4 text-sm font-semibold text-primary-foreground outline-none hover:bg-brand-deep focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              Keep it held
            </button>
            <button
              type="button"
              onClick={() => {
                setConfirmRelease(false)
                void decide('RELEASE', true)
              }}
              className="inline-flex min-h-11 items-center justify-center rounded-lg border border-input px-4 text-sm font-semibold outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              Release payment
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
