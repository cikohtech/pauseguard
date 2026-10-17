// Money and date formatting for the banking mock (Singapore dollars, Singapore time).

const money = new Intl.NumberFormat('en-SG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

/** "S$8,000.00"; `signed` adds "+" / "−" for the transaction list. */
export function formatSgd(amount: number, { signed = false } = {}): string {
  const text = `S$${money.format(Math.abs(amount))}`
  if (!signed) return amount < 0 ? `−${text}` : text
  return `${amount < 0 ? '−' : '+'}${text}`
}

export function formatShortDate(date: Date): string {
  return new Intl.DateTimeFormat('en-SG', {
    day: 'numeric',
    month: 'short',
    timeZone: 'Asia/Singapore',
  }).format(date)
}

export function formatDateTime(date: Date): string {
  return new Intl.DateTimeFormat('en-SG', {
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
    timeZone: 'Asia/Singapore',
  }).format(date)
}

export const daysAgo = (n: number, now = new Date()) => new Date(now.getTime() - n * 86_400_000)

/** The tail of a check ID as a transfer reference: "chk_01M4…ABCD" -> "HB-ABCD1234". */
export const transferRef = (checkId: string | null) =>
  checkId ? `HB-${checkId.slice(-8).toUpperCase()}` : null

/** The hour of day in Singapore, for the greeting. */
export const sgHour = (now = new Date()) =>
  Number(
    new Intl.DateTimeFormat('en-SG', { hour: 'numeric', hourCycle: 'h23', timeZone: 'Asia/Singapore' })
      .format(now)
      .replace(/\D/g, ''),
  )

/** Two-letter initials for an avatar ("Mrs Tan Mei Ling" → "TM"). */
export function initials(name: string) {
  return name
    .replace(/^(Mrs|Mr|Ms|Dr)\.? /, '')
    .split(/\s+/)
    .map((w) => w[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
}
