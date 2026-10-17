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

/**
 * The wall-clock time where the flight is, without the UTC offset, e.g. "11:00 AM". Shown next to an airport code,
 * which already says whose local time it is (the airline convention).
 */
export function formatTime(iso: unknown): string {
  return formatClock(iso).replace(/ \(UTC[^)]*\)$/, '')
}

/** e.g. "Oct 15, 11:00 AM", the airport's local time, without the UTC offset. */
export function formatDateTime(iso: unknown): string {
  return formatLocalTime(iso).replace(/ \(UTC[^)]*\)$/, '')
}

/** e.g. "Fri, Oct 17" for the date line under a flight. */
export function formatDate(iso: unknown): string {
  if (typeof iso !== 'string') return ''
  const m = ISO.exec(iso)
  if (!m) return ''
  const weekday = new Date(Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3]))).getUTCDay()
  return `${['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][weekday]}, ${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}`
}

/** "Mock Air 210" rather than "Mock Air · Mock Air 210" when the flight already names the airline. */
export function flightLabel(airline: string | null | undefined, flight: string | null | undefined): string {
  if (airline && flight) return flight.startsWith(airline) ? flight : `${airline} · ${flight}`
  return airline || flight || 'Flight'
}

/** "1 hour 30 min", "2 hours" or "45 min", for delays. */
export function formatMinutes(minutes: number): string {
  const h = Math.floor(minutes / 60)
  const m = minutes % 60
  const hours = h === 1 ? '1 hour' : `${h} hours`
  return h && m ? `${hours} ${m} min` : h ? hours : `${m} min`
}

export function formatDay(iso: string): string {
  const m = ISO.exec(iso)
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}` : iso
}

/** e.g. "Oct 15 · 8:00 AM" in the timestamp's own zone, for compact cards. */
export function formatShort(iso: unknown): string {
  const full = formatLocalTime(iso)
  const match = /^([A-Z][a-z]{2} \d+), (\d+:\d{2} [AP]M)/.exec(full)
  return match ? `${match[1]} · ${match[2]}` : full
}

export function formatClock(iso: unknown): string {
  return formatLocalTime(iso).replace(/^[A-Z][a-z]{2} \d+, /, '')
}

/** "$80" for whole amounts, "$80.50" otherwise. */
export function formatMoney(amount: number, currency: string): string {
  try {
    const whole = Number.isInteger(amount)
    return new Intl.NumberFormat('en-US', {
      style: 'currency', currency, minimumFractionDigits: whole ? 0 : 2, maximumFractionDigits: 2,
    }).format(amount)
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
