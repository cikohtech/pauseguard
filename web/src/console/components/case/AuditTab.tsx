import type { CaseDetail } from '@/console/api'
import { auditEntries } from '@/console/audit'
import { Section } from '@/console/components/bits'
import { dateTime } from '@/console/format'
import { Icon } from '@/components/icons/Icon'

export function AuditTab({ detail }: { detail: CaseDetail }) {
  const entries = auditEntries(detail)
  return (
    <Section title="Audit trail" icon="history">
      <ol className="flex flex-col">
        {entries.map(({ key, at, who, what, note, icon }, i) => (
          <li key={key} className="relative flex gap-4 pb-5 last:pb-0">
            {i < entries.length - 1 && <span aria-hidden="true" className="absolute top-11 bottom-1 left-[19px] w-0.5 rounded-full bg-outline-variant" />}
            <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-full bg-secondary-container text-on-secondary-container">
              <Icon name={icon} className="size-5" />
            </span>
            <div className="min-w-0 pt-0.5 text-body-m">
              <p>
                <span className="font-medium text-on-surface">{what}</span>
                <span className="text-on-surface-variant"> · {who}</span>
              </p>
              {at && (
                <time dateTime={at.toISOString()} className="text-body-s text-on-surface-variant">
                  {dateTime(at)}
                </time>
              )}
              {note && <p className="mt-1.5 rounded-lg rounded-tl-xs bg-surface-container px-3 py-2 text-body-m break-words">{note}</p>}
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-5 flex items-center gap-2 border-t border-outline-variant/70 pt-3 text-body-s text-on-surface-variant">
        <Icon name="lock" className="size-4" />
        Audit entries are append-only and written by the API; nobody can edit them from the console.
      </p>
    </Section>
  )
}
