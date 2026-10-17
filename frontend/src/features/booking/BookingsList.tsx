/** The bookings list page. Owner: Jian. */
import { useEffect, useState } from 'react'
import type { BookingsApi } from '../../app/dataSource.ts'
import { bookingHref } from '../../app/route.ts'
import type { BookingSummary } from '../../app/types.ts'
import { ApiError } from '../../app/httpApi.ts'
import { DevCreatePanel } from '../dev/DevPanel.tsx'
import { AccessCode } from './AccessCode.tsx'
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
  const [locked, setLocked] = useState<'no' | 'ask' | 'wrong'>('no')

  useEffect(() => {
    let cancelled = false
    api
      .listBookings()
      .then((list) => {
        if (cancelled) return
        setLocked('no')
        setBookings(list)
      })
      .catch((e) => {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 403) setLocked((l) => (l === 'no' ? 'ask' : 'wrong'))
        else if (e instanceof ApiError && e.status === 429) setError(e.message)
        else setError("Couldn't load your bookings. Check your connection, then try again.")
      })
    return () => {
      cancelled = true
    }
  }, [api, reload])

  if (locked !== 'no') {
    return (
      <AccessCode
        wrong={locked === 'wrong'}
        onSubmit={(code) => {
          api.setAccessCode?.(code)
          setReload((n) => n + 1)
        }}
      />
    )
  }

  return (
    <section aria-labelledby="bookings-title">
      <h1 className="page-title" id="bookings-title">Your bookings</h1>
      <p className="muted" style={{ marginBottom: 16 }}>
        Open a booking to see your flight. If something went wrong, Travel Buddy can help you find a new one.
      </p>
      {error && (
        <div className="card" role="alert">
          <p className="error-text" style={{ marginTop: 0 }}>{error}</p>
          <button className="btn btn-small" type="button" style={{ marginTop: 8 }} onClick={() => { setError(''); setReload((n) => n + 1) }}>
            Try again
          </button>
        </div>
      )}
      {!bookings && !error && (
        <div className="stack" aria-busy="true" aria-label="Loading bookings">
          {[0, 1, 2].map((i) => (
            <div className="card skeleton-card" key={i}>
              <span className="skeleton skeleton-title" style={{ width: '30%' }} />
              <span className="skeleton skeleton-line" style={{ width: '45%' }} />
              <span className="skeleton skeleton-line" style={{ width: '60%' }} />
            </div>
          ))}
        </div>
      )}
      {bookings && bookings.length === 0 && (
        <div className="card empty">
          <h2 className="card-title">No bookings yet</h2>
          <p>There are no bookings to show.</p>
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
              <span className="small">Booking ref {b.booking_reference ?? b.booking_id}</span>
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
