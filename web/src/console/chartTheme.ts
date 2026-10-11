// Chart colours as CSS tokens (index.css, "Console charts") and shared axis styling.
export const CHART = {
  GREEN: 'var(--chart-green)',
  AMBER: 'var(--chart-amber)',
  RED: 'var(--chart-red)',
  primary: 'var(--chart-primary)',
  context: 'var(--chart-context)',
  grid: 'var(--chart-grid)',
  axis: 'var(--chart-axis)',
} as const

export const AXIS_TICK = { fill: CHART.axis, fontSize: 12 }
export const AXIS_PROPS = { tickLine: false, axisLine: { stroke: CHART.grid }, tick: AXIS_TICK } as const
