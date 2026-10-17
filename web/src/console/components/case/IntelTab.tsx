import type { CaseDetail, WebFinding } from '@/console/api'
import { Section } from '@/console/components/bits'
import { WATCHLIST_TYPE_LABEL } from '@/console/format'
import { Icon } from '@/components/icons/Icon'
import { cn } from '@/lib/utils'

const RISK_STYLE: Record<WebFinding['risk'], string> = {
  HIGH: 'bg-verdict-red-soft text-verdict-red-ink',
  MEDIUM: 'bg-verdict-amber-soft text-verdict-amber-ink',
  LOW: 'bg-surface-container-high text-on-surface-variant',
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
      className="mt-3 h-16 w-full rounded-lg border-0"
    />
  )
}

export function IntelTab({ detail }: { detail: CaseDetail }) {
  const matches = detail.intel?.watchlist_matches ?? []
  const findings = detail.intel?.web_findings ?? []
  const points = detail.case.case_file?.intel_points ?? []
  return (
    <div className="grid gap-4 @4xl:grid-cols-2">
      <Section title="Watchlist matches" icon="policy">
        {matches.length > 0 ? (
          <div className="-mx-5">
            <table className="w-full text-body-m">
              <thead className="border-y border-outline-variant/70 bg-surface-container-low text-label-l text-on-surface-variant">
                <tr>
                  <th scope="col" className="h-10 px-5 text-left font-medium">Type</th>
                  <th scope="col" className="h-10 px-5 text-left font-medium">Value</th>
                  <th scope="col" className="h-10 px-5 text-left font-medium">Source</th>
                  <th scope="col" className="h-10 px-5 text-right font-medium">Reports</th>
                </tr>
              </thead>
              <tbody>
                {matches.map((m) => (
                  <tr key={`${m.type}-${m.value}`} className="border-b border-outline-variant/50">
                    <td className="h-11 px-5">{WATCHLIST_TYPE_LABEL[m.type]}</td>
                    <td className="h-11 px-5 font-mono text-[13px] break-all">{m.value}</td>
                    <td className="h-11 px-5">{m.source === 'SEED' ? 'Intel feed' : 'Analyst report'}</td>
                    <td className="h-11 px-5 text-right font-medium tabular-nums">{m.reported_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="text-body-m text-on-surface-variant">No phone, link or account in this case is on the watchlist.</p>
        )}
        {points.length > 0 && (
          <ul className="mt-4 flex flex-col gap-2 text-body-m">
            {points.map((p) => (
              <li key={p} className="flex gap-2.5">
                <Icon name="info" className="mt-0.5 size-4 text-primary" />
                {p}
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section
        title="Web findings"
        icon="travel_explore"
        aside={
          <span className="inline-flex items-center gap-1 rounded-full bg-surface-container px-2.5 py-1 text-label-m font-medium text-on-surface-variant">
            <Icon name="search" className="size-3.5" />
            Grounded with Google Search
          </span>
        }
      >
        {findings.length > 0 ? (
          <ul className="flex flex-col gap-0.5">
            {findings.map((w, i) => (
              <li key={i} className="rounded-xs bg-surface-container-low p-4 first:rounded-t-lg last:rounded-b-lg">
                <p className="flex items-start gap-2.5">
                  <span className={cn('mt-0.5 inline-flex h-5 shrink-0 items-center rounded-xs px-1.5 text-label-s font-medium', RISK_STYLE[w.risk])}>
                    {w.risk}
                  </span>
                  <span className="text-body-m text-on-surface">{w.finding}</span>
                </p>
                <p className="mt-1.5 flex items-center gap-1 text-body-s text-on-surface-variant">
                  <Icon name="search" className="size-3.5" />
                  Searched: “{w.query}”
                </p>
                {w.sources.length > 0 && (
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {w.sources.map((url, j) => (
                      <li key={url}>
                        <a
                          href={url}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="ripple inline-flex min-h-8 items-center gap-1.5 rounded-sm border border-outline-variant bg-surface-container-lowest px-2.5 text-label-m font-medium text-primary"
                        >
                          <Icon name="public" className="size-3.5" />
                          {sourceLabel(url, j)}
                          <Icon name="open_in_new" className="size-3.5" />
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
          <p className="text-body-m text-on-surface-variant">
            {detail.case.case_file
              ? 'No grounded web findings for this case.'
              : 'The web search runs after the verdict; findings appear here in a few seconds.'}
          </p>
        )}
      </Section>
    </div>
  )
}
