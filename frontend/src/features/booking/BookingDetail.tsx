/**
 * One booking: the flight card (the trip, what happened, the flights) on top, then the chat with Travel Buddy, with
 * the confirm card shown inside the chat, just above the input. Owner: Jian.
 */
import { useCallback, useEffect, useState } from 'react'
import { ChatSlot } from '../../app/ChatSlot.tsx'
import type { Conversation } from '../../app/conversations.ts'
import type { BookingsApi } from '../../app/dataSource.ts'
import { listHref } from '../../app/route.ts'
import type { BookingDetail as BookingDetailData, BookingSummary, ChatSituation } from '../../app/types.ts'
import { ApiError, OFFLINE, TIMED_OUT } from '../../app/httpApi.ts'
import { EMPTY_CONVERSATION } from '../../app/conversations.ts'
import { DevBookingPanel } from '../dev/DevPanel.tsx'
import { ConfirmCard, type ConfirmProblem } from './ConfirmCard.tsx'
import { FlightCard } from './FlightCard.tsx'

/** What the traveler sees when a message gets no answer, by cause. Never shown as if Travel Buddy said it. */
const CANT_REACH = "Can't reach Travel Buddy. Check your connection, then try again."
const ASSISTANT_DOWN = "Travel Buddy's assistant isn't available right now. Try again in a moment."
const TOO_SLOW = 'Travel Buddy is taking too long to answer. Try again.'
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
  const [loadError, setLoadError] = useState<'not found' | 'failed' | null>(null)
  const [reload, setReload] = useState(0)
  const [sending, setSending] = useState(false)
  // The last message that got no answer, and how many times in a row that happened.
  const [unanswered, setUnanswered] = useState<{ text: string; message: string; failures: number } | null>(null)
  const { messages, card, changes, dismissed } = conversation

  useEffect(() => {
    let cancelled = false
    api
      .getBooking(bookingId)
      .then((d) => !cancelled && setDetail(d))
      .catch((e) => !cancelled && setLoadError(e instanceof ApiError && e.status === 404 ? 'not found' : 'failed'))
    return () => {
      cancelled = true
    }
  }, [api, bookingId, reload])

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

  /** Ask Travel Buddy. The traveler's message is shown once; a retry sends the same text again. */
  const ask = useCallback(
    async (text: string, retry: boolean) => {
      if (!retry) {
        update(bookingId, (c) => ({ ...c, messages: [...c.messages, { role: 'traveler', text }], dismissed: false }))
      }
      setSending(true)
      try {
        const out = await api.chat(bookingId, text)
        if (out.stopped_reason === 'error') throw new ApiError(503, out.reply)
        setUnanswered(null)
        update(bookingId, (c) => ({
          ...c, messages: [...c.messages, { role: 'assistant', text: out.reply }], card: out.confirm_card,
        }))
      } catch (e) {
        const status = e instanceof ApiError ? e.status : null
        const message = status === OFFLINE ? CANT_REACH : status === TIMED_OUT ? TOO_SLOW : ASSISTANT_DOWN
        setUnanswered((u) => ({ text, message, failures: (u?.text === text ? u.failures : 0) + 1 }))
      } finally {
        setSending(false)
      }
    },
    [api, bookingId, update],
  )
  const send = useCallback((text: string) => ask(text, false), [ask])

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
      <section className="booking-page">
        <a className="back" href={listHref}>← All bookings</a>
        <div className="card empty" role="alert">
          {loadError === 'not found' ? (
            <>
              <h1 className="card-title">Booking not found</h1>
              <p>We couldn't find this booking. Go back to your bookings and pick another one.</p>
            </>
          ) : (
            <>
              <h1 className="card-title">Couldn't load this booking</h1>
              <p>Check your connection, then try again.</p>
              <button className="btn btn-small" type="button" style={{ marginTop: 12 }}
                onClick={() => { setLoadError(null); setReload((n) => n + 1) }}>
                Try again
              </button>
            </>
          )}
        </div>
      </section>
    )
  }
  if (!detail) return <BookingSkeleton />

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
      <ChatSlot
        bookingId={bookingId}
        messages={messages}
        sending={sending}
        onSend={send}
        action={action}
        situation={situationOf(detail.summary)}
        travelers={detail.summary.passenger_count}
        problem={unanswered && {
          message: unanswered.message,
          fallback: unanswered.failures >= 2
            ? `Still not working? Contact your airline and give them booking ref ${detail.summary.booking_id}.`
            : undefined,
          retrying: sending,
          onRetry: () => void ask(unanswered.text, true),
        }}
      />
      {api.dev && (
        <DevBookingPanel
          dev={api.dev}
          bookingId={bookingId}
          dataSource={detail.summary.data_source}
          onCleared={() => {
            update(bookingId, () => EMPTY_CONVERSATION)
            setUnanswered(null)
            setReload((n) => n + 1)
          }}
        />
      )}
    </section>
  )
}

function situationOf(summary: BookingSummary): ChatSituation {
  if (summary.rebooked || summary.status === 'rebooked') return 'rebooked'
  if (summary.status === 'canceled' || summary.status === 'delayed' || summary.status === 'on time') return summary.status
  return 'missed'
}

/** The shape of the page while the booking loads, so nothing jumps when it arrives. */
function BookingSkeleton() {
  return (
    <section className="booking-page" aria-busy="true" aria-label="Loading booking">
      <span className="skeleton skeleton-line" style={{ width: 110 }} />
      <div className="card flight-card">
        <span className="skeleton skeleton-title" />
        <span className="skeleton skeleton-line" style={{ width: '30%' }} />
        <span className="skeleton skeleton-block" />
        <span className="skeleton skeleton-line" style={{ width: '60%' }} />
      </div>
      <div className="card">
        <span className="skeleton skeleton-line" style={{ width: '40%' }} />
        <span className="skeleton skeleton-block" style={{ marginTop: 12 }} />
      </div>
    </section>
  )
}
