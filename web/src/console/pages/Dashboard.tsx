import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { consoleApi, type Metrics, type MetricsRange } from '@/console/api'
import { AXIS_PROPS, CHART } from '@/console/chartTheme'
import { ChartCard, DataTable, Legend, TooltipCard } from '@/console/components/charts'
import { TYPOLOGY_LABEL, compactMoney, dateShort, hourLabel, percent, seconds } from '@/console/format'
import { useConsoleTitle } from '@/console/title'
import { Icon, type IconName } from '@/components/icons/Icon'
import { Shape } from '@/components/m3/Expressive'
import { iconButton } from '@/components/m3/styles'
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
      <div className="mx-auto flex max-w-[1320px] flex-col gap-5 px-4 py-6 sm:px-8">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-headline-s text-on-surface">Dashboard</h1>
            <p className="mt-1 flex flex-wrap items-center gap-1.5 text-body-m text-on-surface-variant">
              <span aria-hidden="true" className="relative flex size-2">
                <span className="absolute inline-flex size-full animate-ping rounded-full bg-verdict-green opacity-60 motion-reduce:hidden" />
                <span className="relative inline-flex size-2 rounded-full bg-verdict-green" />
              </span>
              Live checks from the customer app (benchmark runs excluded). Refreshes every 15 s
              {updated && <> · updated {hourLabel(updated)}</>}.
            </p>
          </div>
          <div className="flex items-center gap-2">
            {/* M3 segmented button: the selected segment is tonal and shows a check */}
            <div role="group" aria-label="Time range" className="inline-flex h-10 overflow-hidden rounded-full border border-outline">
              {(['today', '7d'] as const).map((r, i) => (
                <button
                  key={r}
                  type="button"
                  aria-pressed={range === r}
                  onClick={() => setRange(r)}
                  className={cn(
                    'ripple inline-flex min-w-28 items-center justify-center gap-2 px-4 text-label-l font-medium focus-visible:outline-offset-[-3px]',
                    i > 0 && 'border-l border-outline',
                    range === r ? 'bg-secondary-container text-on-secondary-container' : 'text-on-surface',
                  )}
                >
                  {range === r && <Icon name="check" className="size-[18px]" />}
                  {r === 'today' ? 'Today' : 'Last 7 days'}
                </button>
              ))}
            </div>
            <button type="button" onClick={() => setTick((t) => t + 1)} title="Refresh" className={iconButton('outlined', 'size-10')}>
              <Icon name="refresh" className="!size-5" />
              <span className="sr-only">Refresh</span>
            </button>
          </div>
        </div>

        {failed && !metrics && (
          <p role="alert" className="flex items-center gap-2 rounded-lg bg-error-container px-4 py-3 text-body-m text-on-error-container">
            <Icon name="error" className="size-5" />
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

function Tile({
  label,
  value,
  note,
  icon,
  children,
}: {
  label: string
  value: string
  note?: string
  icon: IconName
  children?: React.ReactNode
}) {
  return (
    <div className="flex flex-col rounded-xl border border-outline-variant/80 bg-surface-container-lowest p-5">
      <p className="flex items-center gap-2.5 text-title-s text-on-surface-variant">
        <span className="inline-flex size-9 items-center justify-center rounded-full bg-primary-container text-on-primary-container">
          <Icon name={icon} className="size-5" />
        </span>
        {label}
      </p>
      <p className="mt-3 text-headline-l tracking-[-0.01em] text-on-surface tabular-nums">{value}</p>
      {children}
      {note && <p className="mt-auto pt-2 text-body-s text-on-surface-variant">{note}</p>}
    </div>
  )
}

/** The headline number: money kept from scammers. */
function Hero({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="relative flex flex-col overflow-hidden rounded-xl bg-primary-container p-6 text-on-primary-container sm:col-span-2">
      <Shape shape="cookie12" spin className="pointer-events-none absolute -top-16 -right-14 size-64 text-primary opacity-[0.09]" />
      <p className="relative flex items-center gap-2.5 text-title-m">
        <span className="inline-flex size-9 items-center justify-center rounded-full bg-primary text-on-primary">
          <Icon name="verified_user" fill className="size-5" />
        </span>
        {label}
      </p>
      <p className="relative mt-4 text-display-l tracking-[-0.03em] tabular-nums">{value}</p>
      <p className="relative mt-auto flex items-start gap-2 pt-3 text-body-m opacity-90">
        <Icon name="info" className="mt-0.5 size-4" />
        {note}
      </p>
    </div>
  )
}

function Kpis({ m, range }: { m: Metrics; range: MetricsRange }) {
  const flagged = m.verdicts.RED + m.verdicts.AMBER
  const total = VERDICTS.reduce((n, v) => n + m.verdicts[v], 0)
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" data-testid="kpis">
      <Hero
        label={`Money protected ${range === 'today' ? 'today' : 'in 7 days'}`}
        value={compactMoney(m.money_protected_sgd)}
        note="Held RED transfers not released, plus AMBER transfers the customer paused or cancelled."
      />
      <Tile icon="verified_user" label="Checks" value={m.checks.toLocaleString('en-SG')} note={`${flagged} flagged RED or AMBER`} />
      <Tile icon="bar_chart" label="Verdicts" value={total ? `${m.verdicts.RED} · ${m.verdicts.AMBER} · ${m.verdicts.GREEN}` : '0'} note="RED · AMBER · GREEN">
        {total > 0 && (
          <div className="mt-3 flex h-2 gap-0.5" aria-hidden="true">
            {(['RED', 'AMBER', 'GREEN'] as const).map((v) =>
              m.verdicts[v] ? <span key={v} className="rounded-full" style={{ flexGrow: m.verdicts[v], background: CHART[v] }} /> : null,
            )}
          </div>
        )}
      </Tile>
      <Tile
        icon="rule"
        label="False-positive rate"
        value={m.verdicts.RED ? percent(m.false_positive_rate, 1) : '—'}
        note="RED checks an analyst released ÷ RED checks"
      />
      <Tile
        icon="timer"
        label="Latency p50 / p95"
        value={m.latency_ms.p50 ? `${seconds(m.latency_ms.p50)} / ${seconds(m.latency_ms.p95)}` : '—'}
        note="Customer’s answer → full result (targets 5 s / 10 s)"
      />
      <Tile
        icon="payments"
        label="Cost per check"
        value={m.cost_per_check_usd === null ? 'Not priced' : `US$${m.cost_per_check_usd.toFixed(4)}`}
        note={m.cost_per_check_usd === null ? 'Set from the published Gemini price list' : 'Gemini tokens × list price'}
      />
      <Tile icon="category" label="Typologies seen" value={String(m.top_typologies.length)} note="Distinct scam types in flagged checks (top 5)" />
    </div>
  )
}

function KpiSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4" aria-busy="true" aria-label="Loading metrics">
      {[0, 1, 2, 3, 4, 5, 6].map((i) => (
        <Skeleton key={i} className={cn('h-36 rounded-xl', i === 0 && 'sm:col-span-2')} />
      ))}
    </div>
  )
}

const Empty = ({ text }: { text: string }) => (
  <div className="flex h-full flex-col items-center justify-center gap-2 rounded-lg bg-surface-container-low text-body-m text-on-surface-variant">
    <Icon name="monitoring" className="size-8 opacity-60" />
    {text}
  </div>
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
                cursor={{ fill: 'var(--surface-container)' }}
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
                  stroke="var(--surface-container-lowest)"
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
                cursor={{ fill: 'var(--surface-container)' }}
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
                <LabelList dataKey="count" position="right" className="fill-on-surface text-[12px] font-medium" />
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
                cursor={{ fill: 'var(--surface-container)' }}
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
                  className="fill-on-surface text-[12px] font-medium"
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
