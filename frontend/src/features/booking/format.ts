/** Display helpers for times, money and statuses. Owner: Jian. */

const ISO = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(Z|[+-]\d{2}:\d{2})$/
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Shows the wall-clock time in the timestamp's own zone, e.g. "Oct 15, 11:00 AM (UTC-04:00)". */
export function formatLocalTime(iso: unknown): string {
  if (typeof iso !== 'string') return 'Unknown'
  const m = ISO.exec(iso)
  if (!m) return iso
  const [, , month, day, hour, minute, zone] = m
  const h = Number(hour)
  const clock = `${h % 12 === 0 ? 12 : h % 12}:${minute} ${h < 12 ? 'AM' : 'PM'}`
  return `${MONTHS[Number(month) - 1]} ${Number(day)}, ${clock} (UTC${zone === 'Z' ? '+00:00' : zone})`
}

export function formatDay(iso: string): string {
  const m = ISO.exec(iso)
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}` : iso
}

export function formatClock(iso: unknown): string {
  return formatLocalTime(iso).replace(/^[A-Z][a-z]{2} \d+, /, '')
}

export function formatMoney(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency }).format(amount)
  } catch {
    return `${amount.toFixed(2)} ${currency}`
  }
}

export type Tone = 'danger' | 'warn' | 'success' | 'accent' | 'sim' | 'neutral'

export function statusTone(status: string): Tone {
  if (status === 'rebooked' || status === 'on time') return 'success'
  if (status === 'canceled') return 'danger'
  if (status.startsWith('missed') || status.includes('delay')) return 'warn'
  return 'neutral'
}

export function statusLabel(status: string): string {
  if (status === 'missed by traveler') return 'Missed flight'
  return status.charAt(0).toUpperCase() + status.slice(1)
}
