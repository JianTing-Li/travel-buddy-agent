/**
 * One booking: the flight card (the trip, what happened, the flights) on top, then the chat with Travel Buddy, with
 * the confirm card shown inside the chat, just above the input. Owner: Jian.
 */
import { useCallback, useEffect, useState } from 'react'
import { ChatSlot } from '../../app/ChatSlot.tsx'
import type { Conversation } from '../../app/conversations.ts'
import type { BookingsApi } from '../../app/dataSource.ts'
import { listHref } from '../../app/route.ts'
import type { BookingDetail as BookingDetailData } from '../../app/types.ts'
import { DevBookingPanel } from '../dev/DevPanel.tsx'
import { ConfirmCard, type ConfirmProblem } from './ConfirmCard.tsx'
import { FlightCard } from './FlightCard.tsx'

const CHAT_ERROR = 'Something went wrong on my side. Try sending that again.'
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

  const disrupted = !detail.summary.rebooked
  const action = disrupted && card ? (
    <ConfirmCard card={card} showSource={Boolean(api.dev)} onConfirm={confirm} onCheck={checkStatus} onDismiss={dismissCard} />
  ) : disrupted && dismissed ? (
    <div className="card notice" role="status">
      <h2 className="card-title">No flight chosen yet</h2>
      <p className="muted">Nothing was booked. Tell Travel Buddy what to change, or ask for other options.</p>
    </div>
  ) : null

  return (
    <section className="booking-page">
      <a className="back" href={listHref}>← All bookings</a>
      <FlightCard detail={detail} changes={disrupted ? changes : []} showSource={Boolean(api.dev)} />
      <ChatSlot bookingId={bookingId} messages={messages} sending={sending} onSend={send} action={action} />
      {api.dev && <DevBookingPanel dev={api.dev} bookingId={bookingId} />}
    </section>
  )
}
