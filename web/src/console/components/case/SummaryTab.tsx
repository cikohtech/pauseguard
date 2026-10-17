import type { CaseDetail } from '@/console/api'
import { AiLabel, ConfidenceBar, Section } from '@/console/components/bits'
import { customerAnswer } from '@/console/evidence'
import { ACTION_LABEL, FLAG_LABEL } from '@/console/format'
import { Icon, Sparkle } from '@/components/icons/Icon'
import { Skeleton } from '@/components/ui/skeleton'
import type { CustomerChoice } from '@/lib/api'

const CHOICE_LABEL: Record<CustomerChoice, string> = {
  COOL_OFF: 'Paused the transfer for 24 hours',
  CALLED_CONTACT: 'Called their trusted contact',
  PROCEEDED: 'Sent the money after the warning',
  CANCELLED: 'Cancelled the transfer',
}

export function SummaryTab({ detail }: { detail: CaseDetail }) {
  const file = detail.case.case_file
  const answer = customerAnswer(detail)
  return (
    <div className="grid gap-4 @4xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="flex min-w-0 flex-col gap-4">
        {/* What Gemini wrote, labelled the way Google products label AI output */}
        <section className="ai-border ai-glow rounded-xl p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-title-m text-on-surface">
              <Sparkle />
              Case summary
            </h3>
            <AiLabel>Written by Gemini</AiLabel>
          </div>
          {file ? (
            <p className="text-body-l text-on-surface">{file.summary}</p>
          ) : (
            <div className="flex flex-col gap-2" role="status" aria-label="Writing the case file">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          )}
        </section>

        {file && file.evidence_points.length > 0 && (
          <Section title="Key evidence" icon="format_quote">
            <ul className="flex flex-col gap-0.5">
              {file.evidence_points.map((p, i) => (
                <li
                  key={i}
                  className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xs bg-surface-container-low px-3 py-2.5 first:rounded-t-lg last:rounded-b-lg"
                >
                  <span className="inline-flex h-6 shrink-0 items-center rounded-sm bg-surface-container-highest px-2 text-label-m font-medium text-on-surface">
                    {FLAG_LABEL[p.flag] ?? p.flag}
                  </span>
                  <span className="text-body-m text-on-surface-variant italic">“{p.quote}”</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {file && file.timeline.length > 0 && (
          <Section title="Timeline" icon="history">
            <ol className="relative flex flex-col gap-4 pl-6 before:absolute before:top-2 before:bottom-2 before:left-[7px] before:w-0.5 before:rounded-full before:bg-outline-variant">
              {file.timeline.map((step, i) => (
                <li key={i} className="relative text-body-m text-on-surface">
                  <span
                    aria-hidden="true"
                    className="absolute top-1 -left-6 size-4 rounded-full border-[3px] border-surface-container-lowest bg-primary shadow-[0_0_0_1px_var(--primary)]"
                  />
                  {step}
                </li>
              ))}
            </ol>
          </Section>
        )}
      </div>

      <div className="flex min-w-0 flex-col gap-4">
        <section className="ai-border rounded-xl p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h3 className="flex items-center gap-2 text-title-m text-on-surface">
              <Icon name="task_alt" className="size-5 text-on-surface-variant" />
              Recommended action
            </h3>
            <AiLabel />
          </div>
          {file ? (
            <div className="flex flex-col gap-2">
              <p className="text-headline-s text-primary">{ACTION_LABEL[file.recommended_action]}</p>
              <p className="text-body-m text-on-surface-variant">{file.recommended_reason}</p>
              <ConfidenceBar value={file.confidence} label="Case-file confidence" className="mt-1" />
            </div>
          ) : (
            <Skeleton className="h-16" />
          )}
        </section>

        {detail.fusion && (
          <Section
            title="Why this verdict"
            icon="gavel"
            aside={
              <span className="inline-flex items-center gap-1 rounded-full bg-surface-container px-2.5 py-1 text-label-m font-medium text-on-surface-variant">
                <Icon name="rule" className="size-3.5" /> Rules, not AI
              </span>
            }
          >
            <ul className="flex flex-col gap-2">
              {detail.fusion.reasons.map((r) => (
                <li key={r} className="flex gap-2.5 text-body-m text-on-surface">
                  <Icon name="check" className="mt-0.5 size-4 text-primary" />
                  {r}
                </li>
              ))}
            </ul>
          </Section>
        )}

        <Section title="What the customer said" icon="forum">
          {answer?.text ? (
            <blockquote className="rounded-lg rounded-tl-xs bg-surface-container px-4 py-3 text-body-m text-on-surface">
              {answer.text}
            </blockquote>
          ) : (
            <p className="text-body-m text-on-surface-variant">No answer recorded.</p>
          )}
          <p className="mt-3 flex items-center gap-2 text-body-m">
            <span className="text-on-surface-variant">Customer’s choice:</span>
            <span className="font-medium">{detail.customer_choice ? CHOICE_LABEL[detail.customer_choice] : 'None yet'}</span>
          </p>
        </Section>
      </div>
    </div>
  )
}
