/** One booking: what happened, the original itinerary, the chat slot and the confirm card. Owner: Jian. */
import { useCallback, useEffect, useState } from 'react'
import { ChatSlot } from '../../app/ChatSlot.tsx'
import type { BookingsApi } from '../../app/dataSource.ts'
import { listHref } from '../../app/route.ts'
import type { BookingDetail as BookingDetailData, ChatMessage, ConfirmCard as ConfirmCardData } from '../../app/types.ts'
import { ConfirmCard } from './ConfirmCard.tsx'
import { formatLocalTime, formatMoney } from './format.ts'
import { SourcePill, StatusPill } from './Pills.tsx'

const CHAT_ERROR = "Something went wrong on my side. Try sending that again."

export function BookingDetail({ api, bookingId }: { api: BookingsApi; bookingId: string }) {
  const [detail, setDetail] = useState<BookingDetailData | null>(null)
  const [loadError, setLoadError] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sending, setSending] = useState(false)
  const [card, setCard] = useState<ConfirmCardData | null>(null)

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

  const send = useCallback(
    async (text: string) => {
      setMessages((m) => [...m, { role: 'traveler', text }])
      setSending(true)
      try {
        const out = await api.chat(bookingId, text)
        setMessages((m) => [...m, { role: 'assistant', text: out.reply }])
        setCard(out.confirm_card)
      } catch {
        setMessages((m) => [...m, { role: 'assistant', text: CHAT_ERROR }])
      } finally {
        setSending(false)
      }
    },
    [api, bookingId],
  )

  const confirm = useCallback(
    async (optionId: string): Promise<string | null> => {
      try {
        const out = await api.confirm(bookingId, optionId)
        if (out.status === 'confirmed') {
          setCard(null)
          setDetail(await api.getBooking(bookingId))
          return null
        }
        if (out.status === 'pending') return out.reason ?? 'The result is uncertain. Do not try again yet.'
        setCard(null)
        return out.reason ?? 'That option can no longer be confirmed.'
      } catch {
        return "We couldn't reach the server. Check your connection before trying again."
      }
    },
    [api, bookingId],
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

  return (
    <section aria-labelledby="booking-title">
      <a className="back" href={listHref}>← All bookings</a>

      {summary.rebooked && confirmation ? (
        <div className="banner banner-success" role="status">
          <div>
            <h2>Your rebooking is confirmed (simulated)</h2>
            <p>
              Confirmation {confirmation.confirmation_id}. Additional cost{' '}
              {formatMoney(confirmation.additional_cost, confirmation.currency)}. {confirmation.note}
            </p>
            <p>New departure {formatLocalTime(confirmation.updated_itinerary.departs)} · arrival {formatLocalTime(confirmation.updated_itinerary.arrives)}</p>
          </div>
        </div>
      ) : (
        <div className={`banner ${summary.status === 'canceled' ? '' : 'banner-warn'}`} role="status">
          <div>
            <h2>
              {summary.status === 'canceled' ? 'Your flight was canceled' : 'You missed this flight'}
            </h2>
            <p>Disruption: {summary.disruption_type}. This disruption is simulated.</p>
          </div>
        </div>
      )}

      <div className="detail-grid">
        <div className="stack">
          <div className="card">
            <h1 className="card-title" id="booking-title">Original itinerary</h1>
            <p className="route-line">{summary.origin} to {summary.destination}</p>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <StatusPill status={summary.status} />
              <SourcePill source={summary.data_source} />
            </div>
            <ul className="facts">
              <li><strong>{String(itinerary.flight ?? 'Flight')}</strong></li>
              <li>Departs {formatLocalTime(itinerary.departs)}</li>
              <li>Ref {summary.booking_id}</li>
              <li>
                {summary.passenger_count} {summary.passenger_count === 1 ? 'traveler' : 'travelers'}
                {summary.passenger_count > 1 ? ', all rebooked together on the same flight' : ''}
              </li>
            </ul>
          </div>
          {disrupted && card && <ConfirmCard card={card} onConfirm={confirm} onDismiss={() => setCard(null)} />}
        </div>
        <ChatSlot bookingId={bookingId} messages={messages} sending={sending} onSend={send} />
      </div>
    </section>
  )
}
