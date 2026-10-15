/** The bookings list page. Owner: Jian. */
import { useEffect, useState } from 'react'
import type { BookingsApi } from '../../app/dataSource.ts'
import { bookingHref } from '../../app/route.ts'
import type { BookingSummary } from '../../app/types.ts'
import { DevCreatePanel } from '../dev/DevPanel.tsx'
import { formatDay } from './format.ts'
import { SourcePill, StatusPill } from './Pills.tsx'

export function BookingsList({ api }: { api: BookingsApi }) {
  const [bookings, setBookings] = useState<BookingSummary[] | null>(null)
  const [error, setError] = useState('')
  const [reload, setReload] = useState(0)

  useEffect(() => {
    let cancelled = false
    api
      .listBookings()
      .then((list) => !cancelled && setBookings(list))
      .catch(() => !cancelled && setError("Couldn't load your bookings. Try again."))
    return () => {
      cancelled = true
    }
  }, [api, reload])

  return (
    <section aria-labelledby="bookings-title">
      <h1 className="page-title" id="bookings-title">Your bookings</h1>
      <p className="muted" style={{ marginBottom: 16 }}>
        Open a booking to see what happened and find a replacement flight.
      </p>
      {error && <p className="error-text" role="alert">{error}</p>}
      {!bookings && !error && <p className="muted" role="status">Loading bookings…</p>}
      {bookings && bookings.length === 0 && (
        <div className="card empty">
          <h2 className="card-title">No bookings yet</h2>
          <p>Start a session to see bookings here.</p>
        </div>
      )}
      <div className="stack">
        {bookings?.map((b) => (
          <a className="booking-row" key={b.booking_id} href={bookingHref(b.booking_id)}>
            <div>
              <p className="booking-route">{b.origin} to {b.destination}</p>
              <p className="muted">
                {formatDay(b.departs)} · {b.passenger_count} {b.passenger_count === 1 ? 'traveler' : 'travelers'} · Ref {b.booking_id}
              </p>
            </div>
            <div className="booking-meta">
              <StatusPill status={b.status} />
              <SourcePill source={b.data_source} />
            </div>
          </a>
        ))}
      </div>
      {api.dev && (
        <div className="section">
          <DevCreatePanel dev={api.dev} onCreated={() => setReload((n) => n + 1)} />
        </div>
      )}
    </section>
  )
}
