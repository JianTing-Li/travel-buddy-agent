/** Tiny hash router (#/ and #/bookings/:id) so react-router can replace it later without touching the screens. Owner: Jian. */
import { useSyncExternalStore } from 'react'

export type Route = { name: 'list' } | { name: 'booking'; id: string }

export function parseHash(hash: string): Route {
  const match = /^#\/bookings\/([^/?#]+)/.exec(hash)
  if (match) {
    try {
      return { name: 'booking', id: decodeURIComponent(match[1]) }
    } catch {
      return { name: 'list' }
    }
  }
  return { name: 'list' }
}

export const bookingHref = (id: string): string => `#/bookings/${encodeURIComponent(id)}`
export const listHref = '#/'

function subscribe(onChange: () => void): () => void {
  window.addEventListener('hashchange', onChange)
  return () => window.removeEventListener('hashchange', onChange)
}

export function useHash(): string {
  return useSyncExternalStore(subscribe, () => window.location.hash)
}
