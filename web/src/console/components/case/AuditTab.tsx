import type { CaseDetail } from '@/console/api'
import { auditEntries } from '@/console/audit'
import { Section } from '@/console/components/bits'
import { dateTime } from '@/console/format'

export function AuditTab({ detail }: { detail: CaseDetail }) {
  const entries = auditEntries(detail)
  return (
    <Section title="Audit trail">
      <ol className="flex flex-col">
        {entries.map(({ key, at, who, what, note, icon: Icon }, i) => (
          <li key={key} className="relative flex gap-3 pb-4 last:pb-0">
            {i < entries.length - 1 && <span aria-hidden="true" className="absolute top-8 bottom-0 left-[15px] w-px bg-border" />}
            <span className="inline-flex size-8 shrink-0 items-center justify-center rounded-full bg-muted text-muted-foreground">
              <Icon aria-hidden="true" className="size-4" />
            </span>
            <div className="min-w-0 pt-1 text-sm">
              <p>
                <span className="font-semibold">{what}</span>
                <span className="text-muted-foreground"> · {who}</span>
              </p>
              {at && (
                <time dateTime={at.toISOString()} className="text-xs text-muted-foreground">
                  {dateTime(at)}
                </time>
              )}
              {note && <p className="mt-1 rounded-lg bg-muted px-2.5 py-1.5 text-[13px] break-words">{note}</p>}
            </div>
          </li>
        ))}
      </ol>
      <p className="mt-4 border-t border-border pt-3 text-xs text-muted-foreground">
        Audit entries are append-only and written by the API; nobody can edit them from the console.
      </p>
    </Section>
  )
}
