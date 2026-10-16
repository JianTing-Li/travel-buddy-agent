/**
 * One booking: what happened, a recovery workspace (guidance, the confirm card, the chat slot) and the original
 * booking as a compact side panel. Owner: Jian.
 */
import { useCallback, useEffect, useState } from 'react'
import { ChatSlot } from '../../app/ChatSlot.tsx'
import type { Conversation } from '../../app/conversations.ts'
import type { BookingsApi } from '../../app/dataSource.ts'
import { listHref } from '../../app/route.ts'
import type { BookingDetail as BookingDetailData } from '../../app/types.ts'
import { DevBookingPanel } from '../dev/DevPanel.tsx'
import { cityName } from './airports.ts'
import { ConfirmCard, type ConfirmProblem } from './ConfirmCard.tsx'
import { formatLocalTime, formatMoney } from './format.ts'
import { SourcePill, StatusPill } from './Pills.tsx'

const CHAT_ERROR = 'Something went wrong on my side. Try sending that again.'
const NO_REAL_TICKET = 'No real ticket was issued.'
/** How often the open page asks the app for airline changes. */
const CHANGE_POLL_MS = 8000

interface Props {
  api: BookingsApi
  bookingId: string
  conversation: Conversation
  update: (bookingId: string, change: (current: Conversation) => Conversation) => void
}

export function BookingDetail({ api, bookingId, conversation, update }: Props) {
  const [detail, setDetail] = useState<BookingDetailData | null>(null)
  const [loadError, setLoadError] = useState('')
  const [sending, setSending] = useState(false)
  const { messages, card, changes, dismissed } = conversation

  useEffect(() => {
    let cancelled = false
    api
      .getBooking(bookingId)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => !cancelled && setLoadError("We couldn't find that booking."))
    return () => {
      cancelled = true
    }
  }, [api, bookingId])

  useEffect(() => {
    let cancelled = false
    async function poll() {
      if (document.hidden) return
      try {
        const out = await api.checkChanges(bookingId)
        if (out.new_changes.length === 0) return
        // Saved to the shared store even if this page was left meanwhile: the server shows each change only once,
        // so a change dropped here would never come back.
        update(bookingId, (c) => ({ ...c, changes: [...c.changes, ...out.new_changes] }))
        if (cancelled) return
        const fresh = await api.getBooking(bookingId)
        if (!cancelled) setDetail(fresh)
      } catch {
        // a failed check is simply tried again on the next tick
      }
    }
    void poll()
    const timer = setInterval(poll, CHANGE_POLL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [api, bookingId, update])

  const send = useCallback(
    async (text: string) => {
      update(bookingId, (c) => ({ ...c, messages: [...c.messages, { role: 'traveler', text }], dismissed: false }))
      setSending(true)
      try {
        const out = await api.chat(bookingId, text)
        update(bookingId, (c) => ({
          ...c, messages: [...c.messages, { role: 'assistant', text: out.reply }], card: out.confirm_card,
        }))
      } catch {
        update(bookingId, (c) => ({ ...c, messages: [...c.messages, { role: 'assistant', text: CHAT_ERROR }] }))
      } finally {
        setSending(false)
      }
    },
    [api, bookingId, update],
  )

  const confirm = useCallback(
    async (optionId: string): Promise<ConfirmProblem | null> => {
      try {
        const out = await api.confirm(bookingId, optionId)
        if (out.status === 'confirmed') {
          update(bookingId, (c) => ({ ...c, card: null }))
          setDetail(await api.getBooking(bookingId))
          return null
        }
        if (out.status === 'pending') {
          return { kind: 'pending', message: out.reason ?? 'The result of your rebooking is not known yet.' }
        }
        update(bookingId, (c) => ({ ...c, card: null }))
        return { kind: 'error', message: out.reason ?? 'That option can no longer be confirmed.' }
      } catch {
        // The request may have reached the server, so this is treated as uncertain, never as "try again".
        return {
          kind: 'pending',
          message: "We lost the connection while confirming, so we can't tell yet whether it went through.",
        }
      }
    },
    [api, bookingId, update],
  )

  const checkStatus = useCallback(async () => {
    try {
      const fresh = await api.getBooking(bookingId)
      setDetail(fresh)
      if (fresh.summary.rebooked) update(bookingId, (c) => ({ ...c, card: null }))
    } catch {
      // still unknown; the traveler can check again
    }
  }, [api, bookingId, update])

  const dismissCard = useCallback(
    () => update(bookingId, (c) => ({ ...c, card: null, dismissed: true })),
    [bookingId, update],
  )

  if (loadError) {
    return (
      <section>
        <a className="back" href={listHref}>← All bookings</a>
        <div className="card empty" role="alert">
          <h1 className="card-title">Booking not found</h1>
          <p>{loadError}</p>
        </div>
      </section>
    )
  }
  if (!detail) return <p className="muted" role="status">Loading booking…</p>

  const { summary, trip, confirmation } = detail
  const itinerary = trip.original_itinerary
  const disrupted = !summary.rebooked
  const onTime = summary.status === 'on time'
  const travelers = `${summary.passenger_count} ${summary.passenger_count === 1 ? 'traveler' : 'travelers'}`

  return (
    <section aria-labelledby="booking-title">
      <a className="back" href={listHref}>← All bookings</a>
      <h1 className="page-title" id="booking-title">
        {cityName(summary.origin)} to {cityName(summary.destination)}
      </h1>
      <p className="muted" style={{ marginBottom: 16 }}>{summary.origin} → {summary.destination} · {travelers}</p>

      {disrupted &&
        changes.map((change) => (
          <div className="banner banner-warn" role="status" key={change.change_id}>
            <div>
              <h2>Airline change detected</h2>
              <p>{change.summary} This change is simulated.</p>
            </div>
          </div>
        ))}

      {summary.rebooked && confirmation ? (
        <div className="banner banner-success" role="status">
          <div>
            <h2>Your rebooking is confirmed (simulated)</h2>
            <p>
              Confirmation {confirmation.confirmation_id}. Additional cost{' '}
              {formatMoney(confirmation.additional_cost, confirmation.currency)} for the whole booking.
            </p>
            <p>
              New departure {formatLocalTime(confirmation.updated_itinerary.departs)} · arrival{' '}
              {formatLocalTime(confirmation.updated_itinerary.arrives)}
            </p>
            <p><strong>{NO_REAL_TICKET}</strong> {confirmation.note}</p>
          </div>
        </div>
      ) : onTime ? (
        <div className="banner banner-neutral" role="status">
          <div>
            <h2>No disruption reported</h2>
            <p>This booking is on time. The app keeps checking for airline changes while this page is open.</p>
          </div>
        </div>
      ) : (
        <div className={`banner ${summary.status === 'canceled' ? '' : 'banner-warn'}`} role="status">
          <div>
            <h2>
              {summary.status === 'canceled'
                ? 'Your flight was canceled'
                : summary.status === 'delayed'
                  ? 'Your flight was delayed'
                  : 'You missed this flight'}
            </h2>
            <p>Disruption: {summary.disruption_type}. This disruption is simulated.</p>
          </div>
        </div>
      )}

      <div className="recovery-grid">
        <div className="stack">
          {disrupted && (
            <section className="card recovery" aria-labelledby="recovery-title">
              <h2 className="recovery-title" id="recovery-title">
                {onTime ? 'Want a different flight?' : "Let's find your next flight"}
              </h2>
              <p className="muted">Tell Travel Buddy what you need. It will confirm your limits before it searches.</p>
              <ul className="needs">
                <li><strong>Latest arrival time</strong> and where you need to be</li>
                <li><strong>Most you can pay extra</strong>, for the whole booking</li>
                <li><strong>Connections</strong> you are fine with</li>
              </ul>
              <p className="small">Everyone on the booking stays together on the same flight.</p>
            </section>
          )}
          {disrupted && card && <ConfirmCard card={card} onConfirm={confirm} onCheck={checkStatus} onDismiss={dismissCard} />}
          {disrupted && dismissed && !card && (
            <div className="card notice" role="status">
              <h2 className="card-title">No flight chosen yet</h2>
              <p className="muted">
                Nothing was booked. Tell Travel Buddy what to change, or ask for other options.
              </p>
            </div>
          )}
          <ChatSlot bookingId={bookingId} messages={messages} sending={sending} onSend={send} />
        </div>

        <aside className="card compact" aria-label="Your booking">
          <h2 className="card-title">Your booking</h2>
          <p className="compact-route">{summary.origin} → {summary.destination}</p>
          <div className="pill-row">
            <StatusPill status={summary.status} />
            <SourcePill source={summary.data_source} />
          </div>
          <ul className="facts">
            <li><strong>{String(itinerary.airline ?? itinerary.flight ?? 'Flight')}</strong></li>
            <li>Departs {formatLocalTime(itinerary.departs)}</li>
            <li>{travelers}</li>
            <li className="small">Ref {summary.booking_id}</li>
          </ul>
        </aside>
      </div>

      {api.dev && (
        <div className="section">
          <DevBookingPanel dev={api.dev} bookingId={bookingId} />
        </div>
      )}
    </section>
  )
}
