import { useTranslation } from 'react-i18next'

import { Icon } from '@/components/icons/Icon'
import { STEPS, type Progress } from '@/customer/progress'
import { cn } from '@/lib/utils'

/** "Reading the message ✓ · Checking the payee ✓ · Comparing with known scams …" (UI_SPEC). */
export function StepTicks({ progress }: { progress: Progress }) {
  const { t } = useTranslation()
  const current = STEPS.find((s) => progress[s] === 'active')
  return (
    <>
      <ol className="flex flex-col gap-0.5">
        {STEPS.map((step) => {
          const state = progress[step]
          return (
            <li
              key={step}
              data-testid={`step-${step}`}
              data-state={state}
              className={cn(
                'flex min-h-14 items-center gap-4 rounded-xs px-4 transition-colors duration-300 first:rounded-t-xl last:rounded-b-xl',
                state === 'active' ? 'bg-secondary-container' : 'bg-surface-container-lowest',
              )}
            >
              <span
                aria-hidden="true"
                className={cn(
                  'inline-flex size-7 shrink-0 items-center justify-center rounded-full transition-colors duration-300',
                  state === 'done' && 'pop-in bg-verdict-green text-white',
                  state === 'active' && 'text-primary',
                  state === 'waiting' && 'border-2 border-outline-variant',
                )}
              >
                {state === 'done' && <Icon name="check" className="size-[18px]" />}
                {state === 'active' && <Icon name="progress_activity" className="size-6 motion-safe:animate-spin" />}
              </span>
              <span
                className={cn(
                  'text-body-l',
                  state === 'waiting' && 'text-on-surface-variant',
                  state === 'active' && 'font-medium text-on-secondary-container',
                  state === 'done' && 'text-on-surface',
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
