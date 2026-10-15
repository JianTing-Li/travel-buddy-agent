/** What the screens need from the backend. Owner: Jian. Fixtures and the real HTTP API both implement it. */
import type { BookingDetail, BookingSummary, ChangeCheckOut, ChatOut, ConfirmOut } from './types.ts'

export interface BookingsApi {
  /** Shown in the footer so nobody mistakes sample data for the live API. */
  label: string
  listBookings(): Promise<BookingSummary[]>
  getBooking(bookingId: string): Promise<BookingDetail>
  /** Looks for airline changes since the last check; each change is returned only once. */
  checkChanges(bookingId: string): Promise<ChangeCheckOut>
  chat(bookingId: string, message: string): Promise<ChatOut>
  confirm(bookingId: string, optionId: string): Promise<ConfirmOut>
}
