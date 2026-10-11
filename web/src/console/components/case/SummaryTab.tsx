import { Quote, Scale } from 'lucide-react'

import type { CaseDetail } from '@/console/api'
import { ConfidenceBar, Section } from '@/console/components/bits'
import { customerAnswer } from '@/console/evidence'
import { ACTION_LABEL, FLAG_LABEL } from '@/console/format'
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
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
      <div className="flex min-w-0 flex-col gap-4">
        <Section title="Case summary">
          {file ? (
            <p className="text-[15px] leading-relaxed">{file.summary}</p>
          ) : (
            <div className="flex flex-col gap-2" role="status" aria-label="Writing the case file">
              <Skeleton className="h-4 w-full" />
              <Skeleton className="h-4 w-11/12" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          )}
        </Section>

        {file && file.evidence_points.length > 0 && (
          <Section title="Key evidence">
            <ul className="flex flex-col gap-2">
              {file.evidence_points.map((p, i) => (
                <li key={i} className="flex gap-2 text-sm">
                  <span className="mt-0.5 shrink-0 rounded bg-muted px-1.5 py-0.5 text-xs font-semibold">
                    {FLAG_LABEL[p.flag] ?? p.flag}
                  </span>
                  <span className="text-muted-foreground italic">“{p.quote}”</span>
                </li>
              ))}
            </ul>
          </Section>
        )}

        {file && file.timeline.length > 0 && (
          <Section title="Timeline">
            <ol className="relative flex flex-col gap-3 border-l border-border pl-4">
              {file.timeline.map((step, i) => (
                <li key={i} className="relative text-sm">
                  <span aria-hidden="true" className="absolute top-1.5 -left-[21px] size-2.5 rounded-full border-2 border-card bg-primary" />
                  {step}
                </li>
              ))}
            </ol>
          </Section>
        )}
      </div>

      <div className="flex min-w-0 flex-col gap-4">
        <Section title="Recommended action">
          {file ? (
            <div className="flex flex-col gap-2">
              <p className="text-lg font-semibold">{ACTION_LABEL[file.recommended_action]}</p>
              <p className="text-sm text-muted-foreground">{file.recommended_reason}</p>
              <ConfidenceBar value={file.confidence} label="Case-file confidence" />
            </div>
          ) : (
            <Skeleton className="h-16" />
          )}
        </Section>

        {detail.fusion && (
          <Section
            title="Why this verdict"
            aside={
              <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                <Scale aria-hidden="true" className="size-3.5" /> Rules, not AI
              </span>
            }
          >
            <ul className="flex list-disc flex-col gap-1 pl-4 text-sm">
              {detail.fusion.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </Section>
        )}

        <Section title="What the customer said">
          {answer?.text ? (
            <blockquote className="flex gap-2 text-sm">
              <Quote aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
              <span>{answer.text}</span>
            </blockquote>
          ) : (
            <p className="text-sm text-muted-foreground">No answer recorded.</p>
          )}
          <p className="mt-3 text-sm">
            <span className="text-muted-foreground">Customer’s choice: </span>
            {detail.customer_choice ? CHOICE_LABEL[detail.customer_choice] : 'None yet'}
          </p>
        </Section>
      </div>
    </div>
  )
}
