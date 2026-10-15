/**
 * Per-booking conversation state kept above the pages, so leaving a booking and coming back does not lose it.
 * Owner: Jian.
 *
 * It lives in memory for this tab only (a reload clears it; the server still holds the agent's history). It must
 * outlive the page because the server shows each airline change only once, so a banner lost on navigation would be
 * lost for good.
 */
import { useCallback, useMemo, useState } from 'react'
import type { AirlineChange, ChatMessage, ConfirmCard } from './types.ts'

export interface Conversation {
  messages: ChatMessage[]
  card: ConfirmCard | null
  changes: AirlineChange[]
  /** The traveler declined the option on the card and has not asked for anything since. */
  dismissed: boolean
}

export const EMPTY_CONVERSATION: Conversation = { messages: [], card: null, changes: [], dismissed: false }

export interface ConversationStore {
  get(bookingId: string): Conversation
  update(bookingId: string, change: (current: Conversation) => Conversation): void
}

export function useConversations(): ConversationStore {
  const [all, setAll] = useState<Record<string, Conversation>>({})
  const update = useCallback(
    (bookingId: string, change: (current: Conversation) => Conversation) =>
      setAll((previous) => ({ ...previous, [bookingId]: change(previous[bookingId] ?? EMPTY_CONVERSATION) })),
    [],
  )
  return useMemo(() => ({ get: (id: string) => all[id] ?? EMPTY_CONVERSATION, update }), [all, update])
}
