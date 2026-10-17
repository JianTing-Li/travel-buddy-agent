/**
 * One booking: the flight card (the trip, what happened, the flights) on top, then the chat with Travel Buddy, with
 * the confirm card shown inside the chat, just above the input. Owner: Jian.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { ChatSlot } from '../../app/ChatSlot.tsx'
import type { Conversation } from '../../app/conversations.ts'
import type { BookingsApi } from '../../app/dataSource.ts'
import { listHref } from '../../app/route.ts'
import type {
  BookingDetail as BookingDetailData, BookingSummary, ChatMessage, ChatSituation, Option,
} from '../../app/types.ts'
import { ApiError, OFFLINE, TIMED_OUT } from '../../app/httpApi.ts'
import { EMPTY_CONVERSATION } from '../../app/conversations.ts'
import { DevBookingPanel } from '../dev/DevPanel.tsx'
import { ConfirmCard, type ConfirmProblem } from './ConfirmCard.tsx'
import { FlightCard } from './FlightCard.tsx'
import { flightLabel, formatTime } from './format.ts'

/** What the traveler sees when a message gets no answer, by cause. Never shown as if Travel Buddy said it. */
const CANT_REACH = "Can't reach Travel Buddy. Check your connection, then try again."
const ASSISTANT_DOWN = "Travel Buddy's assistant isn't available right now. Try again in a moment."
const TOO_SLOW = 'Travel Buddy is taking too long to answer. Try again.'
const NOT_KNOWN_YET = "We don't know yet whether your rebooking went through."

/**
 * Why a confirm was refused, for the traveler. The gate's reasons are written for Travel Buddy, so only the
 * "What changed" part (plain facts) is passed on.
 */
function rejectionText(reason: string | null | undefined): string {
  const changed = reason?.split('What changed:')[1]?.trim()
  if (changed) return `This flight changed since you reviewed it: ${changed} Ask Travel Buddy to show it again.`
  if (reason?.includes('outside the traveler')) return 'This flight no longer fits your limits. Ask Travel Buddy for another option.'
  return "This flight can't be confirmed right now. Ask Travel Buddy for another option."
}
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
  const [unanswered, setUnanswered] = useState<{ text: string; id: string; message: string; failures: number } | null>(null)
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

  // A reloaded page starts with an empty conversation in memory: show the one the server kept, once.
  const openedEmpty = useRef(messages.length === 0)  // the page is remounted per booking (keyed by its id)
  useEffect(() => {
    if (!openedEmpty.current) return
    let cancelled = false
    api
      .chatHistory(bookingId)
      .then((history) => {
        if (cancelled || history.messages.length === 0) return
        update(bookingId, (c) => (c.messages.length > 0 ? c : {
          ...c,
          messages: history.messages.map((m) => ({ role: m.role, text: m.text, search: m.search ?? null })),
          card: history.confirm_card,
        }))
      })
      .catch(() => {
        // no history to show; the traveler can still start a new message
      })
    return () => {
      cancelled = true
    }
  }, [api, bookingId, update])

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
    async (text: string, retryOf?: string) => {
      // The same id on a retry lets the server answer a message it already answered instead of running it twice.
      const id = retryOf ?? newMessageId()
      if (!retryOf) {
        update(bookingId, (c) => ({ ...c, messages: [...c.messages, { role: 'traveler', text }], dismissed: false }))
      }
      setSending(true)
      try {
        const out = await api.chat(bookingId, text, id)
        if (out.stopped_reason === 'error') throw new ApiError(503, out.reply)
        setUnanswered(null)
        update(bookingId, (c) => ({
          ...c,
          messages: [...c.messages, { role: 'assistant', text: out.reply, search: out.search ?? null }],
          card: out.confirm_card,
        }))
      } catch (e) {
        const status = e instanceof ApiError ? e.status : null
        const message = status === OFFLINE ? CANT_REACH : status === TIMED_OUT ? TOO_SLOW : ASSISTANT_DOWN
        setUnanswered((u) => ({ text, id, message, failures: (u?.id === id ? u.failures : 0) + 1 }))
      } finally {
        setSending(false)
      }
    },
    [api, bookingId, update],
  )
  const send = useCallback((text: string) => ask(text), [ask])

  /** A card was chosen: mark it, and tell Travel Buddy in words the traveler can read back. */
  const choose = useCallback(
    (messageIndex: number, option: Option) => {
      update(bookingId, (c) => ({
        ...c, messages: c.messages.map((m, i) => (i === messageIndex ? { ...m, chosen: option.option_id } : m)),
      }))
      const d = option.flight_details
      void ask(`I'll take ${flightLabel(d.airline, d.flight)}, leaving ${d.origin} at ${formatTime(d.departs)}.`)
    },
    [ask, bookingId, update],
  )

  const confirm = useCallback(
    async (optionId: string): Promise<ConfirmProblem | null> => {
      try {
        const out = await api.confirm(bookingId, optionId)
        if (out.status === 'confirmed') {
          setDetail(await api.getBooking(bookingId))
          // Say it where the traveler is looking: the card they pressed is replaced by the app's receipt in the chat.
          const note: ChatMessage = { role: 'app', text: out.receipt ?? "You're rebooked." }
          update(bookingId, (c) => ({ ...c, card: null, messages: [...c.messages, note] }))
          return null
        }
        if (out.status === 'pending') return { kind: 'pending', message: NOT_KNOWN_YET }
        update(bookingId, (c) => ({ ...c, card: null }))
        return { kind: 'error', message: rejectionText(out.reason) }
      } catch {
        // The request may have reached the server, so this is treated as uncertain, never as "try again".
        return {
          kind: 'pending',
          message: "We lost the connection while confirming, so we don't know yet whether it went through.",
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
        onChoose={choose}
        action={action}
        situation={situationOf(detail.summary)}
        travelers={detail.summary.passenger_count}
        problem={unanswered && {
          message: unanswered.message,
          fallback: unanswered.failures >= 2
            ? `Still not working? Contact your airline and give them booking ref ${
              detail.summary.booking_reference ?? detail.summary.booking_id}.`
            : undefined,
          retrying: sending,
          onRetry: () => void ask(unanswered.text, unanswered.id),
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

function newMessageId(): string {
  return typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`
}
