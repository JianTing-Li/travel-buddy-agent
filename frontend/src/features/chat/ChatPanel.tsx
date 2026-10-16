/**
 * The chat with Travel Buddy. Owner: Cheich.
 *
 * It only shows messages and collects what the traveler types. The shell owns the conversation and the
 * network calls (see ChatSlotProps in types.ts). Nothing here can book a flight: booking happens only through
 * the confirm card, never through a chat message.
 */
import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import type { ChatSlotProps } from '../../app/types.ts'
import { RichText } from './RichText.tsx'
import './chat.css'

const EXAMPLES = [
  "My flight was canceled. I need to land by 3 PM and I don't want to pay extra.",
  'I missed my flight. I can pay up to $150 extra and want to arrive today.',
  'There are three of us. We need to stay together and land before 3 PM.',
]
const MAX_INPUT_HEIGHT = 160

export function ChatPanel({ bookingId, messages, sending, onSend }: ChatSlotProps) {
  const [draft, setDraft] = useState('')
  const logRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Keep the newest message in view.
  useEffect(() => {
    const log = logRef.current
    if (log) log.scrollTop = log.scrollHeight
  }, [messages.length, sending])

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
    <section className="card chat" aria-label={`Chat with Travel Buddy about booking ${bookingId}`}>
      <div>
        <h2 className="card-title">Chat with Travel Buddy</h2>
        <p className="muted small">Simulated: no real tickets are bought or changed.</p>
      </div>

      <div ref={logRef} className="chat-log" role="log" aria-live="polite" aria-relevant="additions" tabIndex={0}>
        {messages.length === 0 && !sending && (
          <div className="chat-welcome">
            <p>
              Tell me what happened and what you need: how much extra you can pay, when you must arrive, how many
              connections are okay, and how many people are traveling.
            </p>
            <p className="muted small">For example (tap one to edit it first):</p>
            <div className="chat-examples">
              {EXAMPLES.map((example) => (
                <button key={example} type="button" className="chat-chip" onClick={() => pickExample(example)}>
                  {example}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-msg--${m.role}`}>
            <span className="chat-sr">{m.role === 'traveler' ? 'You said: ' : 'Travel Buddy said: '}</span>
            {m.role === 'assistant' ? <RichText text={m.text} /> : m.text}
          </div>
        ))}

        {sending && (
          <div className="chat-msg chat-msg--assistant chat-typing" role="status">
            <span className="chat-sr">Travel Buddy is working on it</span>
            <span className="chat-dots" aria-hidden="true"><i /><i /><i /></span>
          </div>
        )}
      </div>

      <form className="chat-form" onSubmit={onSubmit}>
        <label className="chat-sr" htmlFor={`chat-input-${bookingId}`}>Message Travel Buddy</label>
        <textarea
          id={`chat-input-${bookingId}`}
          ref={inputRef}
          className="chat-input"
          rows={1}
          value={draft}
          placeholder="Tell Travel Buddy what you need…"
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
