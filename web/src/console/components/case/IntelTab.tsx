import { ExternalLink, Globe, ShieldBan } from 'lucide-react'

import type { CaseDetail, WebFinding } from '@/console/api'
import { Section } from '@/console/components/bits'
import { WATCHLIST_TYPE_LABEL } from '@/console/format'
import { cn } from '@/lib/utils'

const RISK_STYLE: Record<WebFinding['risk'], string> = {
  HIGH: 'bg-verdict-red-soft text-verdict-red-ink',
  MEDIUM: 'bg-verdict-amber-soft text-verdict-amber-ink',
  LOW: 'bg-muted text-muted-foreground',
}

function sourceLabel(url: string, i: number): string {
  try {
    const host = new URL(url).hostname.replace(/^www\./, '')
    return host.endsWith('vertexaisearch.cloud.google.com') ? `Source ${i + 1}` : host
  } catch {
    return `Source ${i + 1}`
  }
}

/**
 * Google Search suggestions must be shown next to grounded results (Grounding with Google Search
 * terms). Google's HTML runs in a sandboxed iframe without scripts; its links open in a new tab.
 */
function SearchSuggestions({ html }: { html: string }) {
  return (
    <iframe
      title="Google Search suggestions"
      sandbox="allow-popups allow-popups-to-escape-sandbox"
      srcDoc={`<base target="_blank">${html}`}
      className="mt-2 h-16 w-full rounded-md border-0"
    />
  )
}

export function IntelTab({ detail }: { detail: CaseDetail }) {
  const matches = detail.intel?.watchlist_matches ?? []
  const findings = detail.intel?.web_findings ?? []
  const points = detail.case.case_file?.intel_points ?? []
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <Section
        title="Watchlist matches"
        aside={<ShieldBan aria-hidden="true" className="size-4 text-muted-foreground" />}
      >
        {matches.length > 0 ? (
          <table className="w-full text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th scope="col" className="py-1.5 text-left font-medium">Type</th>
                <th scope="col" className="py-1.5 text-left font-medium">Value</th>
                <th scope="col" className="py-1.5 text-left font-medium">Source</th>
                <th scope="col" className="py-1.5 text-right font-medium">Reports</th>
              </tr>
            </thead>
            <tbody>
              {matches.map((m) => (
                <tr key={`${m.type}-${m.value}`} className="border-t border-border">
                  <td className="py-1.5">{WATCHLIST_TYPE_LABEL[m.type]}</td>
                  <td className="py-1.5 font-mono text-[13px] break-all">{m.value}</td>
                  <td className="py-1.5">{m.source === 'SEED' ? 'Intel feed' : 'Analyst report'}</td>
                  <td className="py-1.5 text-right font-semibold tabular-nums">{m.reported_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="text-sm text-muted-foreground">No phone, link or account in this case is on the watchlist.</p>
        )}
        {points.length > 0 && (
          <ul className="mt-4 flex list-disc flex-col gap-1 border-t border-border pt-3 pl-4 text-sm">
            {points.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Web findings (Google Search)"
        aside={<Globe aria-hidden="true" className="size-4 text-muted-foreground" />}
      >
        {findings.length > 0 ? (
          <ul className="flex flex-col gap-4">
            {findings.map((w, i) => (
              <li key={i} className={cn(i > 0 && 'border-t border-border pt-4')}>
                <p className="flex items-start gap-2">
                  <span className={cn('mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold', RISK_STYLE[w.risk])}>
                    {w.risk}
                  </span>
                  <span className="text-sm">{w.finding}</span>
                </p>
                <p className="mt-1 text-xs text-muted-foreground">Searched: “{w.query}”</p>
                {w.sources.length > 0 && (
                  <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1">
                    {w.sources.map((url, j) => (
                      <li key={url}>
                        <a
                          href={url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="inline-flex min-h-6 items-center gap-1 rounded text-xs font-medium text-primary underline underline-offset-2 outline-none hover:text-brand-deep focus-visible:ring-3 focus-visible:ring-ring/50"
                        >
                          {sourceLabel(url, j)}
                          <ExternalLink aria-hidden="true" className="size-3" />
                          <span className="sr-only">(opens in a new tab)</span>
                        </a>
                      </li>
                    ))}
                  </ul>
                )}
                {w.search_entry_point_html && <SearchSuggestions html={w.search_entry_point_html} />}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">
            {detail.case.case_file
              ? 'No grounded web findings for this case.'
              : 'The web search runs after the verdict; findings appear here in a few seconds.'}
          </p>
        )}
      </Section>
    </div>
  )
}
