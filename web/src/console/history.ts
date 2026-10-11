import type { CaseHistory } from '@/console/api'
import { dateShort, money } from '@/console/format'

export interface HistoryPoint {
  key: string
  label: string
  amount: number
  count: number
  isTransfer: boolean
  valueLabel: string // drawn above the bar: only this transfer is direct-labelled
}

/** The 90 days, then this transfer as its own bar (highlighted and labelled in the chart). */

export function historyPoints(h: CaseHistory): HistoryPoint[] {
  const days = h.days.map((d) => ({
    key: d.day,
    label: dateShort(new Date(`${d.day}T12:00:00+08:00`)),
    amount: d.amount,
    count: d.count,
    isTransfer: false,
    valueLabel: '',
  }))
  const transfer = {
    key: 'transfer',
    label: 'This transfer',
    amount: h.transfer_amount,
    count: 1,
    isTransfer: true,
    valueLabel: money(h.transfer_amount),
  }
  return [...days, transfer]
}
