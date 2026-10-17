/**
 * Where the chat goes. Owner: Jian.
 *
 * Cheich builds the chat in features/chat. It receives ChatSlotProps (see types.ts); this component only hands the
 * props over, so the shell does not change.
 */
import { ChatPanel } from '../features/chat/ChatPanel.tsx'
import type { ChatSlotProps } from './types.ts'

export function ChatSlot(props: ChatSlotProps) {
  return <ChatPanel {...props} />
}
