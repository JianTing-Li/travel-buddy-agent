/**
 * The real backend behind the BookingsApi interface. Owner: Jian.
 *
 * Starts a session on first use and sends its id in X-Session-Id. The id is kept in sessionStorage so a page
 * reload keeps the same simulated bookings; if the server no longer knows it (it restarted), a new session is
 * started once and the call is retried. No secrets live here: the address is public and keys stay on the server.
 */
import type { BookingsApi } from './dataSource.ts'
import {
  SESSION_HEADER,
  type BookingDetail,
  type BookingSummary,
  type ChangeCheckOut,
  type ChatOut,
  type AirlineChange,
  type ConfirmOut,
  type DevBookingCreate,
  type DevBookingOut,
  type DevDisruptIn,
  type DevFaultsOut,
  type SessionOut,
} from './types.ts'

const DEFAULT_BASE_URL = 'http://localhost:8000'
const STORAGE_KEY = 'travel-buddy-session'
const GENERIC_ERROR = 'The server could not complete that request.'

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

function readStored(): string | null {
  try {
    return window.sessionStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStored(sessionId: string | null): void {
  try {
    if (sessionId) window.sessionStorage.setItem(STORAGE_KEY, sessionId)
    else window.sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // without storage a reload simply starts a new session
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json()
    if (body && typeof body === 'object' && 'detail' in body && typeof body.detail === 'string') return body.detail
  } catch {
    // not JSON
  }
  return GENERIC_ERROR
}

export function createHttpApi(
  baseUrl: string = import.meta.env.VITE_API_URL ?? DEFAULT_BASE_URL,
  fetchImpl: typeof fetch = (...args) => fetch(...args),
): BookingsApi {
  const base = baseUrl.replace(/\/+$/, '')
  let sessionPromise: Promise<string> | null = null

  async function createSession(): Promise<string> {
    const response = await fetchImpl(`${base}/sessions`, { method: 'POST' })
    if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
    const body = (await response.json()) as SessionOut
    writeStored(body.session_id)
    return body.session_id
  }

  function ensureSession(): Promise<string> {
    sessionPromise ??= Promise.resolve(readStored()).then((stored) => stored ?? createSession())
    return sessionPromise
  }

  async function call(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
    const sessionId = await ensureSession()
    const headers: Record<string, string> = { [SESSION_HEADER]: sessionId }
    if (init.body) headers['Content-Type'] = 'application/json'
    const response = await fetchImpl(`${base}${path}`, { ...init, headers })
    if (response.status === 401 && retry) {
      sessionPromise = null
      writeStored(null)
      return call(path, init, false)
    }
    return response
  }

  async function json<T>(response: Response, accepted: number[] = [200]): Promise<T> {
    if (!accepted.includes(response.status)) throw new ApiError(response.status, await errorMessage(response))
    return (await response.json()) as T
  }

  const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

  return {
    label: `Connected to the Travel Buddy API at ${base}.`,
    listBookings: async () => json<BookingSummary[]>(await call('/bookings')),
    getBooking: async (bookingId) => json<BookingDetail>(await call(`/bookings/${encodeURIComponent(bookingId)}`)),
    checkChanges: async (bookingId) =>
      json<ChangeCheckOut>(await call(`/bookings/${encodeURIComponent(bookingId)}/changes/check`, { method: 'POST' })),
    chat: async (bookingId, message) =>
      json<ChatOut>(await call('/chat', post({ booking_id: bookingId, message }))),
    // 200 confirmed, 202 pending and 409 rejected all carry the outcome in the body.
    confirm: async (bookingId, optionId) =>
      json<ConfirmOut>(await call('/confirm', post({ booking_id: bookingId, option_id: optionId })), [200, 202, 409]),
    // Test-data tools: off unless the build sets VITE_DEV_PANEL=true, and they only work against dev_app.
    dev:
      import.meta.env.VITE_DEV_PANEL === 'true'
        ? {
            createBooking: async (body: DevBookingCreate) =>
              json<DevBookingOut>(await call('/dev/bookings', post(body)), [201]),
            disrupt: async (bookingId: string, body: DevDisruptIn) =>
              json<AirlineChange>(await call(`/dev/bookings/${encodeURIComponent(bookingId)}/disrupt`, post(body)), [201]),
            setFaults: async (bookingId: string, faults: string[]) =>
              json<DevFaultsOut>(await call(`/dev/bookings/${encodeURIComponent(bookingId)}/faults`, post({ faults }))),
          }
        : undefined,
  }
}
