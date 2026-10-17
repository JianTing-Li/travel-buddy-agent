/**
 * The top of a booking page: the trip, what happened to it, and the flight(s). After a rebooking the new flight
 * leads and the original is shown below it as replaced. Owner: Jian.
 */
import type { AirlineChange, BookingDetail } from '../../app/types.ts'
import { cityName } from './airports.ts'
import { flightLabel, formatDate, formatMinutes, formatMoney, formatTime } from './format.ts'
import { SourcePill, StatusPill } from './Pills.tsx'

interface Props {
  detail: BookingDetail
  /** Airline changes the app found while the page was open. */
  changes: AirlineChange[]
  /** Dev mode: also show where the data comes from (mock or Duffel test). */
  showSource: boolean
}

export function FlightCard({ detail, changes, showSource }: Props) {
  const { summary, trip, confirmation } = detail
  const itinerary = trip.original_itinerary
  const travelers = `${summary.passenger_count} ${summary.passenger_count === 1 ? 'traveler' : 'travelers'}`
  const rebooked = summary.rebooked && confirmation
  const status = statusText(summary.status, trip.disruption_details.delay_minutes)

  return (
    <section className="card flight-card" aria-labelledby="booking-title">
      <div className="flight-head">
        <div>
          <h1 className="page-title" id="booking-title">
            {cityName(summary.origin)} to {cityName(summary.destination)}
          </h1>
          <p className="muted">{formatDate(itinerary.departs)} · {travelers}</p>
        </div>
        <div className="pill-row">
          <StatusPill status={summary.status} />
          {showSource && <SourcePill source={summary.data_source} />}
        </div>
      </div>

      {rebooked ? (
        <div className="flight-status flight-status--success" role="status">
          <h2>You're rebooked</h2>
          <p>
            Confirmation {confirmation.confirmation_id}. Extra cost{' '}
            {formatMoney(confirmation.additional_cost, confirmation.currency)} for the whole booking.
          </p>
        </div>
      ) : (
        <div className={`flight-status flight-status--${status.tone}`} role="status">
          <h2>{status.title}</h2>
          <p>{status.text}</p>
        </div>
      )}

      {!summary.rebooked &&
        changes.map((change) => (
          <div className="flight-status flight-status--warn" role="status" key={change.change_id}>
            <h2>Airline change</h2>
            <p>{change.summary}</p>
          </div>
        ))}

      {rebooked && (
        <FlightRow
          label="New flight"
          airline={flightLabel(confirmation.updated_itinerary.airline, confirmation.updated_itinerary.flight)}
          origin={confirmation.updated_itinerary.origin}
          destination={confirmation.updated_itinerary.destination}
          departs={confirmation.updated_itinerary.departs}
          arrives={confirmation.updated_itinerary.arrives}
          duration={confirmation.updated_itinerary.duration}
          connections={confirmation.updated_itinerary.connections}
        />
      )}
      <FlightRow
        label={rebooked ? 'Original flight (replaced)' : 'Your flight'}
        replaced={Boolean(rebooked)}
        airline={flightLabel(itinerary.airline, itinerary.flight)}
        origin={itinerary.origin}
        destination={itinerary.destination}
        departs={itinerary.departs}
        arrives={itinerary.arrives}
      />

      <p className="small flight-ref">Booking ref {itinerary.booking_reference ?? summary.booking_id}</p>
    </section>
  )
}

interface RowProps {
  label: string
  airline: string
  origin: string
  destination: string
  departs: string
  arrives: string | null
  duration?: string | null
  connections?: number
  replaced?: boolean
}

function FlightRow({ label, airline, origin, destination, departs, arrives, duration, connections, replaced }: RowProps) {
  const stops = connections === undefined ? null : connections === 0 ? 'Nonstop' : `${connections} connection${connections === 1 ? '' : 's'}`
  const middle = [duration, stops].filter(Boolean).join(' · ')
  return (
    <div className={`flight-row${replaced ? ' flight-row--replaced' : ''}`}>
      <p className="flight-row-label">{label} · {airline}</p>
      <div className="flight-line" aria-hidden="true">
        <div className="flight-end">
          <span className="flight-time">{formatTime(departs)}</span>
          <span className="flight-airport">{origin}</span>
          <span className="small">{cityName(origin)}</span>
        </div>
        <div className="flight-path">
          <span className="small">{middle}</span>
          <span className="flight-path-line" />
        </div>
        <div className="flight-end flight-end--arrive">
          {/* the original arrival time is not always known; a blank keeps the airports lined up */}
          <span className={`flight-time${arrives ? '' : ' flight-time--blank'}`}>{arrives ? formatTime(arrives) : '\u00a0'}</span>
          <span className="flight-airport">{destination}</span>
          <span className="small">{cityName(destination)}</span>
        </div>
      </div>
      <p className="sr-only">
        {label}: departs {origin} {formatDate(departs)} at {formatTime(departs)}
        {arrives ? `, arrives ${destination} at ${formatTime(arrives)}` : `, to ${destination}`}. {middle}
      </p>
    </div>
  )
}

type Tone = 'danger' | 'warn' | 'neutral'

function statusText(status: string, delayMinutes: number | null): { tone: Tone; title: string; text: string } {
  if (status === 'canceled') {
    return { tone: 'danger', title: 'Your flight was canceled', text: 'Travel Buddy can find you a replacement flight below.' }
  }
  if (status === 'delayed') {
    const by = delayMinutes ? ` by about ${formatMinutes(delayMinutes)}` : ''
    return { tone: 'warn', title: `Your flight is delayed${by}`, text: 'If the new time doesn\'t work for you, Travel Buddy can look for another flight.' }
  }
  if (status.startsWith('missed')) {
    return { tone: 'warn', title: 'You missed this flight', text: 'Travel Buddy can find you the next flight that works.' }
  }
  return { tone: 'neutral', title: 'Your flight is on time', text: "We'll show any airline change here while this page is open." }
}
