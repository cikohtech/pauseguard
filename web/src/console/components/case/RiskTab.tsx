import { useEffect, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import { consoleApi, type CaseDetail, type CaseHistory } from '@/console/api'
import { historyPoints, type HistoryPoint } from '@/console/history'
import { Section } from '@/console/components/bits'
import { AXIS_PROPS, CHART } from '@/console/chartTheme'
import { ChartCard, DataTable, TooltipCard } from '@/console/components/charts'
import { compactMoney, dateShort, money, percent } from '@/console/format'
import { Skeleton } from '@/components/ui/skeleton'
import type { Verdict } from '@/lib/api'
import { cn } from '@/lib/utils'

// Thresholds of the transaction score (AGENTS_SPEC §1): below 30 a known payee takes the GREEN
// fast path (a new payee always gets the check-in); the rules-only baseline: ≥ 40 AMBER, ≥ 70 RED.
const BANDS = [
  { from: 70, label: 'High', color: CHART.RED },
  { from: 40, label: 'Elevated', color: CHART.AMBER },
  { from: 0, label: 'Low', color: CHART.GREEN },
]

export function RiskGauge({ score }: { score: number }) {
  const band = BANDS.find((b) => score >= b.from)!
  const r = 70
  const len = Math.PI * r
  const filled = (Math.min(100, Math.max(0, score)) / 100) * len
  const tick = (v: number) => {
    const a = Math.PI * (1 - v / 100)
    return { x1: 90 + (r - 12) * Math.cos(a), y1: 90 - (r - 12) * Math.sin(a), x2: 90 + (r + 12) * Math.cos(a), y2: 90 - (r + 12) * Math.sin(a) }
  }
  return (
    <div className="flex flex-col items-center">
      <svg viewBox="0 0 180 104" className="w-full max-w-[220px]" role="img" aria-label={`Transaction risk score ${score} of 100, ${band.label.toLowerCase()}`}>
        <path d="M 20 90 A 70 70 0 0 1 160 90" fill="none" stroke="var(--surface-container-high)" strokeWidth="14" strokeLinecap="round" />
        <path
          d="M 20 90 A 70 70 0 0 1 160 90"
          fill="none"
          stroke={band.color}
          strokeWidth="14"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${len}`}
        />
        {[40, 70].map((v) => (
          <line key={v} {...tick(v)} stroke="var(--surface-container-lowest)" strokeWidth="3" />
        ))}
        <text x="90" y="80" textAnchor="middle" className="fill-on-surface text-[34px]">
          {score}
        </text>
        <text x="90" y="99" textAnchor="middle" className="fill-on-surface-variant text-[11px]">
          of 100
        </text>
      </svg>
      <p className="mt-2 inline-flex items-center gap-1.5 rounded-full bg-surface-container px-3 py-1 text-label-l font-medium text-on-surface">
        <span aria-hidden="true" className="size-2.5 rounded-full" style={{ background: band.color }} />
        {band.label} transaction risk
      </p>
    </div>
  )
}

const DEST: Record<string, string> = {
  LOCAL_BANK: 'Local bank',
  OVERSEAS: 'Overseas',
  CRYPTO_EXCHANGE: 'Crypto exchange',
  MERCHANT: 'Merchant',
  PAYNOW: 'PayNow',
}

export function RiskTab({ detail }: { detail: CaseDetail }) {
  const risk = detail.txn_risk
  const f = risk?.features ?? null
  const points = (codes: string[]) =>
    risk?.reasons.filter((r) => codes.includes(r.code)).reduce((n, r) => n + r.points, 0) ?? 0
  const rows: { feature: string; value: string; points: number }[] = f
    ? [
        { feature: 'New payee', value: f.is_new_payee ? 'Yes, first payment' : 'No', points: points(['NEW_PAYEE']) },
        {
          feature: 'Amount vs 90-day median',
          value: f.amount_vs_median_90d === null ? 'No history' : `${f.amount_vs_median_90d.toFixed(1)}×`,
          points: points(['AMOUNT_SPIKE']),
        },
        { feature: 'Destination', value: DEST[f.dest_type] ?? f.dest_type, points: points(['CRYPTO_DESTINATION', 'OVERSEAS_DESTINATION']) },
        { feature: 'New payees in 24 h', value: String(f.transfers_to_new_payees_24h), points: points(['NEW_PAYEE_VELOCITY']) },
        { feature: 'Local time', value: `${String(f.hour_local).padStart(2, '0')}:00`, points: points(['NIGHT_TIME']) },
        { feature: 'Customer age', value: f.customer_age === null ? 'Unknown' : String(f.customer_age), points: points(['SENIOR_CUSTOMER']) },
        { feature: 'Share of balance', value: f.balance_share === null ? 'Unknown' : percent(f.balance_share), points: points(['HIGH_BALANCE_SHARE']) },
        { feature: 'Payee on watchlist', value: f.watchlist_hit ? 'Yes' : 'No', points: points(['WATCHLIST_MATCH']) },
      ]
    : []
  const sum = rows.reduce((n, r) => n + r.points, 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 @2xl:grid-cols-[260px_minmax(0,1fr)]">
        <Section title="Transaction score" icon="speed">
          {risk ? <RiskGauge score={risk.score} /> : <p className="text-body-m text-on-surface-variant">Not scored.</p>}
          <p className="mt-3 text-center text-body-s text-on-surface-variant">BigQuery features · deterministic rules</p>
        </Section>
        <Section title="What the score is made of" icon="table">
          {f ? (
            <div className="-mx-5 -mb-5">
              <table className="w-full text-body-m">
                <thead className="border-y border-outline-variant/70 bg-surface-container-low text-label-l text-on-surface-variant">
                  <tr>
                    <th scope="col" className="h-10 px-5 text-left font-medium">Feature</th>
                    <th scope="col" className="h-10 px-5 text-left font-medium">Value</th>
                    <th scope="col" className="h-10 px-5 text-right font-medium">Points</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.feature} className="border-b border-outline-variant/50 transition-colors hover:bg-surface-container-low">
                      <td className="h-11 px-5">{r.feature}</td>
                      <td className={cn('h-11 px-5', r.points > 0 && 'font-medium')}>{r.value}</td>
                      <td className="h-11 px-5 text-right tabular-nums">
                        {r.points > 0 ? (
                          <span className="inline-flex h-6 min-w-9 items-center justify-center rounded-sm bg-primary-container px-1.5 text-label-l font-medium text-on-primary-container">
                            +{r.points}
                          </span>
                        ) : (
                          <span className="text-on-surface-variant">0</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr>
                    <th scope="row" colSpan={2} className="h-12 px-5 text-left text-title-s">
                      Score {sum > 100 && <span className="font-normal text-on-surface-variant">(capped at 100)</span>}
                    </th>
                    <td className="h-12 px-5 text-right text-title-m tabular-nums">{risk?.score}</td>
                  </tr>
                </tfoot>
              </table>
            </div>
          ) : (
            <p className="text-body-m text-on-surface-variant">No features recorded.</p>
          )}
        </Section>
      </div>
      <HistoryChart caseId={detail.case.case_id} verdict={detail.case.verdict} ratio={f?.amount_vs_median_90d ?? null} />
    </div>
  )
}

function HistoryChart({ caseId, verdict, ratio }: { caseId: string; verdict: Verdict; ratio: number | null }) {
  const [history, setHistory] = useState<CaseHistory | null>(null)
  const [failed, setFailed] = useState(false)
  useEffect(() => {
    let live = true
    consoleApi
      .history(caseId)
      .then((h) => live && setHistory(h))
      .catch(() => live && setFailed(true))
    return () => {
      live = false
    }
  }, [caseId])

  const accent = verdict === 'RED' ? CHART.RED : verdict === 'AMBER' ? CHART.AMBER : CHART.primary
  const subtitle = history
    ? `Daily outgoing payments, 90 days to ${dateShort(new Date(history.as_of))}.${
        history.median_debit_90d !== null ? ` Median payment ${money(history.median_debit_90d)}` : ''
      }${ratio ? `; this transfer is ${ratio.toFixed(1)}× that.` : '.'}`
    : 'Daily outgoing payments in the 90 days before this transfer.'

  if (failed) {
    return (
      <Section title="90-day outgoing payments" icon="bar_chart">
        <p className="text-body-m text-on-surface-variant">The payment history couldn’t be loaded.</p>
      </Section>
    )
  }
  if (!history) {
    return (
      <Section title="90-day outgoing payments" icon="bar_chart">
        <Skeleton className="h-[220px]" />
      </Section>
    )
  }
  const data = historyPoints(history)
  const ticks = data.filter((_, i) => i % 14 === 0).map((d) => d.key)
  return (
    <ChartCard
      title="90-day outgoing payments"
      subtitle={subtitle}
      chart={
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 22, right: 44, bottom: 0, left: 0 }} barCategoryGap={1} title="90-day outgoing payments" aria-label={subtitle}>
            <CartesianGrid vertical={false} stroke={CHART.grid} />
            <XAxis dataKey="key" ticks={[...ticks, 'transfer']} tickFormatter={(k: string) => data.find((d) => d.key === k)?.label ?? ''} {...AXIS_PROPS} interval={0} />
            <YAxis tickFormatter={(v: number) => compactMoney(v)} width={64} {...AXIS_PROPS} axisLine={false} />
            <Tooltip
              cursor={{ fill: 'var(--surface-container)' }}
              content={({ active, payload }) => {
                const p = active ? (payload?.[0]?.payload as HistoryPoint | undefined) : undefined
                if (!p) return null
                return (
                  <TooltipCard
                    title={p.label}
                    rows={[
                      { label: p.isTransfer ? 'Amount' : 'Outgoing', value: money(p.amount) },
                      ...(p.isTransfer ? [] : [{ label: 'Payments', value: String(p.count) }]),
                    ]}
                  />
                )
              }}
            />
            <Bar dataKey="amount" maxBarSize={24} radius={[2, 2, 0, 0]} isAnimationActive={false}>
              {data.map((d) => (
                <Cell key={d.key} fill={d.isTransfer ? accent : CHART.context} />
              ))}
              <LabelList dataKey="valueLabel" position="top" offset={6} className="fill-on-surface text-[12px] font-medium" />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      }
      table={
        <DataTable
          head={['Day', 'Payments', 'Outgoing']}
          rows={data
            .filter((d) => d.amount > 0)
            .map((d) => [d.isTransfer ? <strong key="t">This transfer</strong> : d.label, String(d.count), money(d.amount)])}
        />
      }
    />
  )
}
