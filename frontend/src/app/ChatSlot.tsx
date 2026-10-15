/**
 * EMPTY slot where the chat goes. Owner: Jian.
 *
 * Cheich builds the chat in features/chat. It receives ChatSlotProps (see types.ts) and replaces this component's
 * body; the shell does not change. Nothing here sends or shows messages.
 */
import type { ChatSlotProps } from './types.ts'

export function ChatSlot({ bookingId }: ChatSlotProps) {
  return (
    <section className="card slot" aria-label={`Chat slot for booking ${bookingId}`}>
      <h2 className="card-title">Chat with Travel Buddy</h2>
      <p className="muted">The chat goes here.</p>
    </section>
  )
}
