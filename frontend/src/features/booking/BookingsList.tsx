/** The bookings list page. Owner: Jian. */
import { useEffect, useState } from 'react'
import type { BookingsApi } from '../../app/dataSource.ts'
import { bookingHref } from '../../app/route.ts'
import type { BookingSummary } from '../../app/types.ts'
import { DevCreatePanel } from '../dev/DevPanel.tsx'
import { cityName } from './airports.ts'
import { formatShort } from './format.ts'
import { SourcePill, StatusPill } from './Pills.tsx'

/** The action the card offers depends on where the booking stands. */
function actionLabel(booking: BookingSummary): string {
  if (booking.rebooked) return 'View confirmation'
  if (booking.status === 'on time') return 'View booking'
  return 'Find a replacement'
}

export function BookingsList({ api, onReset }: { api: BookingsApi; onReset: () => void }) {
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
        Open a disrupted booking and Travel Buddy will help you find a replacement flight.
      </p>
      {error && (
        <div className="card" role="alert">
          <p className="error-text" style={{ marginTop: 0 }}>{error}</p>
          <button className="btn btn-small" type="button" style={{ marginTop: 8 }} onClick={() => { setError(''); setReload((n) => n + 1) }}>
            Try again
          </button>
        </div>
      )}
      {!bookings && !error && <p className="muted" role="status">Loading bookings…</p>}
      {bookings && bookings.length === 0 && (
        <div className="card empty">
          <h2 className="card-title">No bookings yet</h2>
          <p>Start a session to see bookings here.</p>
        </div>
      )}
      <div className="stack">
        {bookings?.map((b) => (
          <a className="booking-card" key={b.booking_id} href={bookingHref(b.booking_id)}>
            <div className="booking-top">
              <p className="booking-route">{b.origin} → {b.destination}</p>
              <div className="booking-meta">
                <StatusPill status={b.status} />
                {api.dev && <SourcePill source={b.data_source} />}
              </div>
            </div>
            <p className="booking-cities">{cityName(b.origin)} to {cityName(b.destination)}</p>
            <p className="muted">
              {formatShort(b.departs)}
              {b.airline ? ` · ${b.airline}` : ''} · {b.passenger_count} {b.passenger_count === 1 ? 'traveler' : 'travelers'}
            </p>
            <div className="booking-foot">
              <span className="small">Ref {b.booking_id}</span>
              <span className="booking-action">{actionLabel(b)} →</span>
            </div>
          </a>
        ))}
      </div>
      {api.dev && (
        <div className="section">
          <DevCreatePanel
            dev={api.dev}
            onCreated={() => setReload((n) => n + 1)}
            onReset={() => {
              onReset()
              setReload((n) => n + 1)
            }}
          />
        </div>
      )}
    </section>
  )
}
