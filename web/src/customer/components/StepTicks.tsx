import { Check, Circle, LoaderCircle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

import { STEPS, type Progress } from '@/customer/progress'
import { cn } from '@/lib/utils'

/** "Reading the message ✓ · Checking the payee ✓ · Comparing with known scams …" (UI_SPEC). */
export function StepTicks({ progress }: { progress: Progress }) {
  const { t } = useTranslation()
  const current = STEPS.find((s) => progress[s] === 'active')
  return (
    <>
      <ol className="flex flex-col gap-1">
        {STEPS.map((step) => {
          const state = progress[step]
          return (
            <li
              key={step}
              data-testid={`step-${step}`}
              data-state={state}
              className="flex min-h-12 items-center gap-3 rounded-xl px-3"
            >
              <span
                aria-hidden="true"
                className={cn(
                  'inline-flex size-7 items-center justify-center rounded-full transition-colors duration-300',
                  state === 'done' && 'bg-verdict-green-ink text-white',
                  state === 'active' && 'bg-primary-soft text-primary',
                  state === 'waiting' && 'text-muted-foreground/60',
                )}
              >
                {state === 'done' && <Check className="size-4" strokeWidth={3} />}
                {state === 'active' && <LoaderCircle className="size-4 motion-safe:animate-spin" strokeWidth={2.5} />}
                {state === 'waiting' && <Circle className="size-5" />}
              </span>
              <span
                className={cn(
                  'text-[16px]',
                  state === 'waiting' ? 'text-muted-foreground' : 'font-medium text-foreground',
                )}
              >
                {t(`customer.analysing.steps.${step}`)}
                <span className="sr-only">: {t(`customer.analysing.state.${state}`)}</span>
              </span>
            </li>
          )
        })}
      </ol>
      <p role="status" className="sr-only">
        {current ? t(`customer.analysing.steps.${current}`) : ''}
      </p>
    </>
  )
}
