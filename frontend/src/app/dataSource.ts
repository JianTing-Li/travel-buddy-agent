/** What the screens need from the backend. Owner: Jian. Fixtures and the real HTTP API both implement it. */
import type {
  AirlineChange,
  BookingDetail,
  BookingSummary,
  ChangeCheckOut,
  ChatHistoryOut,
  ChatOut,
  ConfirmOut,
  DevBookingCreate,
  DevBookingOut,
  DevDisruptIn,
  DevDuffelBookingIn,
  DevFaultsOut,
  DevResetOut,
} from './types.ts'

/** Test-data tools. Only present when the dev panel is switched on; the backend must be started as dev_app. */
export interface DevApi {
  createBooking(body: DevBookingCreate): Promise<DevBookingOut>
  /** Creates a real Duffel TEST order and adds it to the session. */
  createDuffelBooking(body: DevDuffelBookingIn): Promise<BookingSummary>
  disrupt(bookingId: string, body: DevDisruptIn): Promise<AirlineChange>
  /** Puts a mock booking back to normal (on time) and starts its chat over. */
  clearDisruption(bookingId: string): Promise<BookingSummary>
  setFaults(bookingId: string, faults: string[]): Promise<DevFaultsOut>
  /** Starts this session over with its first mock bookings. Other sessions are untouched. */
  reset(): Promise<DevResetOut>
}

export interface BookingsApi {
  /** Sample data is always flagged in the footer; the live API's address is shown only with the dev panel. */
  kind: 'sample' | 'live'
  label: string
  listBookings(): Promise<BookingSummary[]>
  getBooking(bookingId: string): Promise<BookingDetail>
  /** Looks for airline changes since the last check; each change is returned only once. */
  checkChanges(bookingId: string): Promise<ChangeCheckOut>
  /** messageId is reused when the same message is sent again, so the server answers it only once. */
  chat(bookingId: string, message: string, messageId?: string): Promise<ChatOut>
  /** The conversation so far as the traveler saw it (empty for a new one). */
  chatHistory(bookingId: string): Promise<ChatHistoryOut>
  confirm(bookingId: string, optionId: string): Promise<ConfirmOut>
  dev?: DevApi
  /** A deployed demo may need an access code to start a session; the app sends it from then on. */
  setAccessCode?(code: string): void
}
