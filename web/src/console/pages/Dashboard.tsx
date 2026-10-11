import { RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { consoleApi, type Metrics, type MetricsRange } from '@/console/api'
import { AXIS_PROPS, CHART } from '@/console/chartTheme'
import { ChartCard, DataTable, Legend, TooltipCard } from '@/console/components/charts'
import { TYPOLOGY_LABEL, compactMoney, dateShort, hourLabel, percent, seconds } from '@/console/format'
import { useConsoleTitle } from '@/console/title'
import { Skeleton } from '@/components/ui/skeleton'
import type { Verdict } from '@/lib/api'
import { cn } from '@/lib/utils'

export const REFRESH_MS = 15_000
const VERDICTS: Verdict[] = ['GREEN', 'AMBER', 'RED'] // stack order, bottom to top
const VERDICT_LEGEND = [
  { label: 'RED · held', color: CHART.RED },
  { label: 'AMBER · paused', color: CHART.AMBER },
  { label: 'GREEN · proceeded', color: CHART.GREEN },
]

// /console/dashboard (UI_SPEC Area 2, item 3; PRD A5): KPI tiles and three charts from /metrics.
export function Dashboard() {
  useConsoleTitle('Dashboard')
  const [range, setRange] = useState<MetricsRange>('today')
  const [loaded, setLoaded] = useState<{ range: MetricsRange; metrics: Metrics; at: Date } | null>(null)
  const [failed, setFailed] = useState(false)
  const metrics = loaded?.range === range ? loaded.metrics : null
  const updated = loaded?.range === range ? loaded.at : null

  const [tick, setTick] = useState(0) // the refresh button bumps it

  useEffect(() => {
    let live = true
    const load = () =>
      consoleApi
        .metrics(range)
        .then((m) => {
          if (!live) return
          setLoaded({ range, metrics: m, at: new Date() })
          setFailed(false)
        })
        .catch(() => live && setFailed(true))
    void load()
    const id = setInterval(() => void load(), REFRESH_MS)
    return () => {
      live = false
      clearInterval(id)
    }
  }, [range, tick])

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto flex max-w-[1280px] flex-col gap-5 px-4 py-5 sm:px-6">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Dashboard</h1>
            <p className="text-sm text-muted-foreground">
              Live checks from the customer app (benchmark runs excluded). Refreshes every 15 s
              {updated && <> · updated {hourLabel(updated)}</>}.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div role="group" aria-label="Time range" className="inline-flex rounded-lg border border-border bg-card p-0.5">
              {(['today', '7d'] as const).map((r) => (
                <button
                  key={r}
                  type="button"
                  aria-pressed={range === r}
                  onClick={() => setRange(r)}
                  className={cn(
                    'min-h-10 rounded-md px-3 text-sm font-medium outline-none focus-visible:ring-3 focus-visible:ring-ring/50',
                    range === r ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
                  )}
                >
                  {r === 'today' ? 'Today' : 'Last 7 days'}
                </button>
              ))}
            </div>
            <button
              type="button"
              onClick={() => setTick((t) => t + 1)}
              className="inline-flex size-10 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground outline-none hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <RefreshCw aria-hidden="true" className="size-4" />
              <span className="sr-only">Refresh</span>
            </button>
          </div>
        </div>

        {failed && !metrics && (
          <p role="alert" className="rounded-lg bg-verdict-red-soft px-3 py-2 text-sm text-verdict-red-ink">
            The metrics couldn’t be loaded. Retrying every 15 seconds.
          </p>
        )}
        {metrics ? <Kpis m={metrics} range={range} /> : !failed && <KpiSkeleton />}
        {metrics && (
          <div className="grid gap-4 lg:grid-cols-2">
            <VerdictsChart m={metrics} range={range} className="lg:col-span-2" />
            <TypologyChart m={metrics} />
            <LatencyChart m={metrics} />
          </div>
        )}
      </div>
    </div>
  )
}

function Tile({ label, value, note, hero = false, children }: { label: string; value: string; note?: string; hero?: boolean; children?: React.ReactNode }) {
  return (
    <div className={cn('flex flex-col rounded-xl border border-border bg-card p-4', hero && 'bg-primary-soft sm:col-span-2')}>
      <p className="text-sm text-muted-foreground">{label}</p>
      <p className={cn('mt-1 font-semibold tracking-tight', hero ? 'text-5xl text-brand-deep' : 'text-2xl')}>{value}</p>
      {children}
      {note && <p className="mt-auto pt-2 text-xs text-muted-foreground">{note}</p>}
    </div>
  )
}

function Kpis({ m, range }: { m: Metrics; range: MetricsRange }) {
  const flagged = m.verdicts.RED + m.verdicts.AMBER
  const total = VERDICTS.reduce((n, v) => n + m.verdicts[v], 0)
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" data-testid="kpis">
      <Tile
        hero
        label={`Money protected ${range === 'today' ? 'today' : 'in 7 days'}`}
        value={compactMoney(m.money_protected_sgd)}
        note="Held RED transfers not released, plus AMBER transfers the customer paused or cancelled."
      />
      <Tile label="Checks" value={m.checks.toLocaleString('en-SG')} note={`${flagged} flagged RED or AMBER`} />
      <Tile label="Verdicts" value={total ? `${m.verdicts.RED} · ${m.verdicts.AMBER} · ${m.verdicts.GREEN}` : '0'} note="RED · AMBER · GREEN">
        {total > 0 && (
          <div className="mt-2 flex h-2 gap-0.5 overflow-hidden rounded-full" aria-hidden="true">
            {(['RED', 'AMBER', 'GREEN'] as const).map((v) =>
              m.verdicts[v] ? <span key={v} style={{ flexGrow: m.verdicts[v], background: CHART[v] }} /> : null,
            )}
          </div>
        )}
      </Tile>
      <Tile
        label="False-positive rate"
        value={m.verdicts.RED ? percent(m.false_positive_rate, 1) : '—'}
        note="RED checks an analyst released ÷ RED checks"
      />
      <Tile
        label="Latency p50 / p95"
        value={m.latency_ms.p50 ? `${seconds(m.latency_ms.p50)} / ${seconds(m.latency_ms.p95)}` : '—'}
        note="Customer’s answer → full result (targets 5 s / 10 s)"
      />
      <Tile
        label="Cost per check"
        value={m.cost_per_check_usd === null ? 'Not priced' : `US$${m.cost_per_check_usd.toFixed(4)}`}
        note={m.cost_per_check_usd === null ? 'Set from the published Gemini price list' : 'Gemini tokens × list price'}
      />
      <Tile label="Typologies seen" value={String(m.top_typologies.length)} note="Distinct scam types in flagged checks (top 5)" />
    </div>
  )
}

function KpiSkeleton() {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true" aria-label="Loading metrics">
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <Skeleton key={i} className={cn('h-28 rounded-xl', i === 0 && 'sm:col-span-2')} />
      ))}
    </div>
  )
}

const Empty = ({ text }: { text: string }) => (
  <div className="flex h-full items-center justify-center rounded-lg bg-muted/50 text-sm text-muted-foreground">{text}</div>
)

function VerdictsChart({ m, range, className }: { m: Metrics; range: MetricsRange; className?: string }) {
  const label = (start: string) => (range === 'today' ? hourLabel(new Date(start)) : dateShort(new Date(start)))
  const data = m.verdicts_over_time.map((b) => ({ ...b, label: label(b.start) }))
  const any = data.some((d) => d.GREEN + d.AMBER + d.RED > 0)
  return (
    <ChartCard
      className={className}
      title="Verdicts over time"
      subtitle={range === 'today' ? 'Checks per hour, Singapore time' : 'Checks per day, Singapore time'}
      legend={<Legend items={VERDICT_LEGEND} />}
      chart={
        any ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: 0 }} aria-label="Verdicts over time, stacked by verdict">
              <CartesianGrid vertical={false} stroke={CHART.grid} />
              <XAxis dataKey="label" {...AXIS_PROPS} minTickGap={12} />
              <YAxis allowDecimals={false} width={36} {...AXIS_PROPS} axisLine={false} />
              <Tooltip
                cursor={{ fill: 'var(--muted)' }}
                content={({ active, payload, label: l }) =>
                  active && payload?.length ? (
                    <TooltipCard
                      title={String(l)}
                      rows={(['RED', 'AMBER', 'GREEN'] as const).map((v) => ({
                        label: v,
                        value: String((payload[0].payload as Record<Verdict, number>)[v]),
                        color: CHART[v],
                      }))}
                    />
                  ) : null
                }
              />
              {VERDICTS.map((v, i) => (
                <Bar
                  key={v}
                  dataKey={v}
                  stackId="v"
                  fill={CHART[v]}
                  stroke="var(--card)"
                  strokeWidth={2}
                  maxBarSize={24}
                  radius={i === VERDICTS.length - 1 ? [4, 4, 0, 0] : 0}
                  isAnimationActive={false}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <Empty text={range === 'today' ? 'No checks yet today. Try the customer app.' : 'No checks in the last 7 days.'} />
        )
      }
      table={
        <DataTable
          head={[range === 'today' ? 'Hour' : 'Day', 'RED', 'AMBER', 'GREEN']}
          rows={data.map((d) => [d.label, String(d.RED), String(d.AMBER), String(d.GREEN)])}
        />
      }
    />
  )
}

function TypologyChart({ m }: { m: Metrics }) {
  const data = m.top_typologies.map((t) => ({ name: TYPOLOGY_LABEL[t.typology], count: t.count }))
  return (
    <ChartCard
      title="Top scam typologies"
      subtitle="RED and AMBER checks, by the evidence agent’s typology"
      chart={
        data.length ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} layout="vertical" margin={{ top: 0, right: 32, bottom: 0, left: 0 }} aria-label="Top scam typologies">
              <CartesianGrid horizontal={false} stroke={CHART.grid} />
              <XAxis type="number" allowDecimals={false} {...AXIS_PROPS} axisLine={false} />
              <YAxis type="category" dataKey="name" width={150} {...AXIS_PROPS} />
              <Tooltip
                cursor={{ fill: 'var(--muted)' }}
                content={({ active, payload }) =>
                  active && payload?.length ? (
                    <TooltipCard
                      title={String((payload[0].payload as { name: string }).name)}
                      rows={[{ label: 'Checks', value: String(payload[0].value) }]}
                    />
                  ) : null
                }
              />
              <Bar dataKey="count" fill={CHART.primary} maxBarSize={20} radius={[0, 4, 4, 0]} isAnimationActive={false}>
                <LabelList dataKey="count" position="right" className="fill-foreground text-[12px] font-semibold" />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <Empty text="No flagged checks yet." />
        )
      }
      table={<DataTable head={['Typology', 'Checks']} rows={data.map((d) => [d.name, String(d.count)])} />}
    />
  )
}

function binLabel(from: number, to: number | null) {
  return to === null ? `${from / 1000} s+` : `${from / 1000}–${to / 1000} s`
}

function LatencyChart({ m }: { m: Metrics }) {
  const data = m.latency_histogram.map((b) => ({ label: binLabel(b.from_ms, b.to_ms), count: b.count }))
  const any = data.some((d) => d.count > 0)
  return (
    <ChartCard
      title="Latency"
      subtitle={
        any
          ? `Customer’s answer → full result. p50 ${seconds(m.latency_ms.p50)}, p95 ${seconds(m.latency_ms.p95)}.`
          : 'Customer’s answer → full result'
      }
      chart={
        any ? (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 18, right: 8, bottom: 0, left: 0 }} aria-label="Latency histogram">
              <CartesianGrid vertical={false} stroke={CHART.grid} />
              <XAxis dataKey="label" {...AXIS_PROPS} interval={0} fontSize={11} />
              <YAxis allowDecimals={false} width={36} {...AXIS_PROPS} axisLine={false} />
              <Tooltip
                cursor={{ fill: 'var(--muted)' }}
                content={({ active, payload, label }) =>
                  active && payload?.length ? (
                    <TooltipCard title={String(label)} rows={[{ label: 'Checks', value: String(payload[0].value) }]} />
                  ) : null
                }
              />
              <Bar dataKey="count" fill={CHART.primary} maxBarSize={24} radius={[4, 4, 0, 0]} isAnimationActive={false}>
                <LabelList
                  dataKey="count"
                  position="top"
                  className="fill-foreground text-[12px] font-semibold"
                  formatter={(v: unknown) => (Number(v) > 0 ? String(v) : '')}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        ) : (
          <Empty text="No check-ins answered yet." />
        )
      }
      table={<DataTable head={['Latency', 'Checks']} rows={data.map((d) => [d.label, String(d.count)])} />}
    />
  )
}
