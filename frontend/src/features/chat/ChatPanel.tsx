/**
 * The chat with Travel Buddy. Owner: Cheich.
 *
 * It only shows messages and collects what the traveler types. The shell owns the conversation and the
 * network calls (see ChatSlotProps in types.ts). Nothing here can book a flight: booking happens only through
 * the confirm card, never through a chat message.
 */
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import type { ChatSituation, ChatSlotProps } from '../../app/types.ts'
import { OptionCards } from './OptionCards.tsx'
import { RichText } from './RichText.tsx'
import './chat.css'

/** The welcome text and tap-to-edit examples, by what happened to the booking. */
const WELCOME: Record<ChatSituation, { intro: string; examples: string[] }> = {
  canceled: {
    intro: "Let's find you a new flight. Tell me what you need:",
    examples: [
      "I need to land by 3 PM and don't want to pay extra.",
      'Any flight today works. I can pay up to $100 more.',
      'Nonstop only, please. I have to arrive before 6 PM.',
    ],
  },
  missed: {
    intro: "Let's get you on the next flight that works. Tell me what you need:",
    examples: [
      'I can pay up to $150 extra and need to arrive today.',
      'What is the next flight I can take without paying more?',
      'I need to be there by 10 PM. One connection is fine.',
    ],
  },
  delayed: {
    intro: "If the new time doesn't work for you, tell me what you need:",
    examples: [
      'The delay makes me too late. I need to land by 3 PM.',
      'Is there an earlier flight at no extra cost?',
      "I'll keep this flight unless something gets me in before noon.",
    ],
  },
  'on time': {
    intro: 'Want a different flight? Tell me what you need:',
    examples: [
      'Is there an earlier flight? I can pay up to $100 more.',
      "I'd like to arrive before 5 PM, nonstop only.",
      'Can I move to a later flight at no extra cost?',
    ],
  },
  rebooked: {
    intro: "You're rebooked. Ask me anything about your new flight.",
    examples: ['When does my new flight land?', 'What changed from my original booking?'],
  },
}
const MAX_INPUT_HEIGHT = 160

export function ChatPanel(
  { bookingId, messages, sending, onSend, onChoose, action, situation, travelers, problem }: ChatSlotProps,
) {
  const welcome = WELCOME[situation]
  const [draft, setDraft] = useState('')
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const lastRef = useRef<HTMLDivElement>(null)
  const typingRef = useRef<HTMLDivElement>(null)
  const seen = useRef(messages.length)
  const slow = useSlow(sending)
  // Only the newest cards can be chosen; older ones stay as a record of what was shown.
  const latestSearch = messages.reduce((latest, m, i) => (m.search ? i : latest), -1)

  // Bring what is new into view: the traveler's message and the typing dots, then the START of Travel Buddy's reply
  // (a long reply read from its end is hard to follow). Nothing moves when the page first opens with a history.
  useEffect(() => {
    const grew = messages.length > seen.current
    seen.current = messages.length
    if (!grew && !sending) return
    const smooth = window.matchMedia('(prefers-reduced-motion: no-preference)').matches ? 'smooth' : 'auto'
    const reply = !sending && messages[messages.length - 1]?.role === 'assistant'
    const target = sending ? typingRef.current : lastRef.current
    target?.scrollIntoView({ block: reply ? 'start' : 'nearest', behavior: smooth })
  }, [messages, sending])

  const grow = (el: HTMLTextAreaElement) => {
    el.style.height = 'auto'
    el.style.height = `${Math.min(el.scrollHeight, MAX_INPUT_HEIGHT)}px`
  }

  const submit = () => {
    const text = draft.trim()
    if (!text || sending) return
    onSend(text)
    setDraft('')
    if (inputRef.current) inputRef.current.style.height = 'auto'
  }

  const onSubmit = (e: FormEvent) => {
    e.preventDefault()
    submit()
  }

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends, Shift+Enter adds a line. Never send while an input method is still composing text.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      submit()
    }
  }

  const pickExample = (text: string) => {
    setDraft(text)
    requestAnimationFrame(() => {
      const el = inputRef.current
      if (el) {
        el.focus()
        grow(el)
      }
    })
  }

  return (
    <section className="card chat" aria-labelledby={`chat-title-${bookingId}`}>
      <div className="chat-head">
        <span className="ai-avatar ai-avatar--large" aria-hidden="true">✦</span>
        <div>
          <h2 className="card-title" id={`chat-title-${bookingId}`}>Travel Buddy</h2>
          <p className="small">Your AI travel assistant</p>
        </div>
        <span className="pill pill-ai">AI</span>
      </div>

      <div className="chat-log" role="log" aria-live="polite" aria-relevant="additions">
        {messages.length === 0 && !sending && (
          <div className="chat-welcome">
            <div className="chat-turn">
              <span className="ai-avatar" aria-hidden="true">✦</span>
              <div className="chat-msg chat-msg--assistant">
                <p>{welcome.intro}</p>
                {situation !== 'rebooked' && (
                  <ul className="chat-needs">
                    <li><strong>When you must arrive</strong></li>
                    <li><strong>The most you can pay extra</strong> for the whole booking</li>
                    <li><strong>How many connections</strong> are okay</li>
                  </ul>
                )}
              </div>
            </div>
            {travelers > 1 && situation !== 'rebooked' && (
              <p className="muted small">All {travelers} travelers stay together on the same flight.</p>
            )}
            <p className="muted small">Try one (you can edit it first):</p>
            <div className="chat-examples">
              {welcome.examples.map((example) => (
                <button key={example} type="button" className="chat-chip" onClick={() => pickExample(example)}>
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => {
          const last = i === messages.length - 1 ? lastRef : undefined
          if (m.role === 'app') {
            return (
              <div key={i} ref={last} className="chat-receipt" role="status">
                <span className="chat-receipt-icon" aria-hidden="true">✓</span>
                <p>{m.text}</p>
              </div>
            )
          }
          if (m.role === 'traveler') {
            return (
              <div key={i} ref={last} className="chat-msg chat-msg--traveler">
                <span className="chat-sr">You said: </span>
                {m.text}
              </div>
            )
          }
          // The avatar marks where Travel Buddy starts speaking, not every bubble.
          const first = messages[i - 1]?.role !== 'assistant'
          return (
            <div key={i} ref={last} className="chat-turn">
              {first ? <span className="ai-avatar" aria-hidden="true">✦</span> : <span className="ai-avatar-space" />}
              <div className="chat-turn-body">
                <div className="chat-msg chat-msg--assistant">
                  <span className="chat-sr">Travel Buddy said: </span>
                  <RichText text={m.text} />
                </div>
                {m.search && onChoose && (
                  <OptionCards
                    search={m.search}
                    chosen={m.chosen}
                    active={i === latestSearch && !sending}
                    onChoose={(option) => onChoose(i, option)}
                  />
                )}
              </div>
            </div>
          )
        })}

        {sending && (
          <div ref={typingRef} className="chat-turn" role="status">
            <span className="ai-avatar ai-avatar--thinking" aria-hidden="true">✦</span>
            <div className="chat-msg chat-msg--assistant chat-typing">
              <span className="chat-dots" aria-hidden="true"><i /><i /><i /></span>
              <span className="chat-typing-text">{slow ? 'Still working on it…' : 'Thinking…'}</span>
            </div>
          </div>
        )}
      </div>

      {problem && !sending && (
        <div className="chat-problem" role="alert">
          <p>{problem.message}</p>
          {problem.fallback && <p className="small">{problem.fallback}</p>}
          <button className="btn btn-small" type="button" onClick={problem.onRetry} aria-busy={problem.retrying}>
            Try again
          </button>
        </div>
      )}

      {action && <div className="chat-action">{action}</div>}

      <form className="chat-form" onSubmit={onSubmit}>
        <label className="chat-sr" htmlFor={`chat-input-${bookingId}`}>Message Travel Buddy</label>
        <textarea
          id={`chat-input-${bookingId}`}
          ref={inputRef}
          className="chat-input"
          rows={1}
          value={draft}
          placeholder="Message Travel Buddy…"
          onChange={(e) => {
            setDraft(e.target.value)
            grow(e.target)
          }}
          onKeyDown={onKeyDown}
        />
        <button type="submit" className="btn btn-primary" disabled={!draft.trim() || sending} aria-busy={sending}>
          {sending ? 'Sending…' : 'Send'}
        </button>
      </form>
    </section>
  )
}

/** True once a reply has taken longer than a few seconds, so the wait says it is still going. */
function useSlow(sending: boolean): boolean {
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    if (!sending) return
    const timer = window.setTimeout(() => setSlow(true), 8000)
    return () => {
      window.clearTimeout(timer)
      setSlow(false)
    }
  }, [sending])
  return slow
}
