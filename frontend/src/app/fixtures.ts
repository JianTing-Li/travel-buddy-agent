/**
 * SAMPLE data for the screens, mirroring the four PRD eval cases. Owner: Jian.
 *
 * Nothing here comes from a server and everything is simulated. Dates are relative to today so they never go stale.
 * The "agent" is a script: it asks a question on the first message, then recommends one option (none for case 4).
 */
import type { BookingsApi } from './dataSource.ts'
import type {
  BookingDetail,
  BookingSummary,
  ChatOut,
  ConfirmCard,
  ConfirmOut,
  Confirmation,
  Option,
} from './types.ts'

function dateAt(dayOffset: number, time: string, utcOffset: string): string {
  const day = new Date()
  day.setDate(day.getDate() + dayOffset)
  const yyyy = day.getFullYear()
  const mm = String(day.getMonth() + 1).padStart(2, '0')
  const dd = String(day.getDate()).padStart(2, '0')
  return `${yyyy}-${mm}-${dd}T${time}${utcOffset}`
}

function option(
  id: string,
  flight: string,
  dayOffset: number,
  departs: string,
  arrives: string,
  duration: string,
  cost: number,
  extra: Record<string, unknown> = {},
): Option {
  return {
    option_id: id,
    flight_details: {
      airline: 'Mock Air (SIMULATED)',
      flight,
      origin: 'JFK',
      destination: 'LAX',
      departs: dateAt(dayOffset, departs, '-04:00'),
      arrives: dateAt(dayOffset, arrives, '-07:00'),
      duration,
      connections: 0,
      simulated: true,
      ...extra,
    },
    eligibility: 'eligible',
    additional_cost: cost,
    currency: 'USD',
    validity: 'valid',
    data_source: 'mock',
  }
}

interface Sample {
  summary: BookingSummary
  passengers: number
  recommended: Option | null
  reply: string
}

const SAMPLES: Sample[] = [
  {
    summary: {
      booking_id: 'MOCK-CASE-1', origin: 'JFK', destination: 'LAX', departs: dateAt(0, '08:00', '-04:00'),
      passenger_count: 1, status: 'canceled', disruption_type: 'airline cancellation', data_source: 'mock',
      rebooked: false,
    },
    passengers: 1,
    recommended: option('opt-1a', 'Mock Air 210', 0, '11:00', '14:00', '6h 0m', 0),
    reply:
      'The best fit is Mock Air 210: a nonstop that lands at 2:00 PM Pacific, before your 3 PM deadline, at no additional cost. ' +
      'The 1:00 PM arrival with one connection also fits, but you prefer nonstop. Review the details below and confirm if you want it.',
  },
  {
    summary: {
      booking_id: 'MOCK-CASE-2', origin: 'JFK', destination: 'LAX', departs: dateAt(0, '08:00', '-04:00'),
      passenger_count: 1, status: 'missed by traveler', disruption_type: 'missed flight', data_source: 'mock',
      rebooked: false,
    },
    passengers: 1,
    recommended: option('opt-2a', 'Mock Air 250', 0, '14:00', '17:00', '6h 0m', 80),
    reply:
      'Your booking allows two replacements and none is free. Mock Air 250 lands at 5:00 PM for $80 extra; the other lands at 3:00 PM ' +
      'for $140 extra. Paying $60 less means arriving two hours later. I can’t promise a reimbursement.',
  },
  {
    summary: {
      booking_id: 'MOCK-CASE-3', origin: 'JFK', destination: 'LAX', departs: dateAt(1, '08:00', '-04:00'),
      passenger_count: 3, status: 'canceled', disruption_type: 'airline cancellation', data_source: 'mock',
      rebooked: false,
    },
    passengers: 3,
    recommended: option('opt-3b', 'Mock Air 520', 1, '11:00', '14:00', '6h 0m', 120, {
      cost_applies_to: 'all three travelers',
    }),
    reply:
      'No free option lands before 3 PM, so with your approved limit of $150 the best fit is Mock Air 520: a nonstop landing at 2:00 PM ' +
      'for $120 extra for all three of you. Everyone stays together on the same flight.',
  },
  {
    summary: {
      booking_id: 'MOCK-CASE-4', origin: 'JFK', destination: 'LAX', departs: dateAt(0, '08:00', '-04:00'),
      passenger_count: 1, status: 'canceled', disruption_type: 'airline cancellation', data_source: 'mock',
      rebooked: false,
    },
    passengers: 1,
    recommended: null,
    reply:
      'Only one replacement came back, and it costs $200 extra, above your $100 limit, so I can’t recommend it. ' +
      'Do you want to change a limit, or should I prepare a simulated support handoff?',
  },
]

const QUESTION =
  'I found your booking (sample data). Before I search, what is the latest time you must land, and is your extra-cost limit firm? ' +
  'Tell me about any connection limits too.'

const DELAY_MS = 450
const wait = <T,>(value: T): Promise<T> => new Promise((resolve) => setTimeout(() => resolve(value), DELAY_MS))

export function createFixtureApi(): BookingsApi {
  const state = new Map(
    SAMPLES.map((s) => [
      s.summary.booking_id,
      { sample: s, summary: { ...s.summary }, turns: 0, confirmation: null as Confirmation | null },
    ]),
  )
  const find = (id: string) => {
    const entry = state.get(id)
    if (!entry) throw new Error('Booking not found.')
    return entry
  }

  return {
    label: 'Sample data. Nothing here comes from a server.',

    listBookings: () => wait([...state.values()].map((e) => ({ ...e.summary }))),

    getBooking(id): Promise<BookingDetail> {
      const entry = find(id)
      const s = entry.summary
      return wait({
        summary: { ...s },
        trip: {
          original_itinerary: {
            booking_id: id, flight: 'Mock Air 100', origin: s.origin, destination: s.destination,
            departs: s.departs, status: s.status,
          },
          passengers: Array.from({ length: entry.sample.passengers }, (_, i) => ({ name: `Passenger ${i + 1}` })),
          disruption_details: { type: s.disruption_type, simulated: true },
          data_source: 'mock',
        },
        confirmation: entry.confirmation,
      })
    },

    chat(id): Promise<ChatOut> {
      const entry = find(id)
      entry.turns += 1
      if (entry.turns === 1 || entry.confirmation) {
        return wait({ reply: entry.confirmation ? 'Your simulated rebooking is done.' : QUESTION, stopped_reason: 'reply', confirm_card: null })
      }
      const option = entry.sample.recommended
      const card: ConfirmCard | null = option
        ? {
            booking_id: id, option, validation_result: 'valid', changes_to_review: [],
            simulated: true, notice: 'Simulated rebooking. No real ticket is issued.',
          }
        : null
      return wait({ reply: entry.sample.reply, stopped_reason: 'reply', confirm_card: card })
    },

    confirm(id, optionId): Promise<ConfirmOut> {
      const entry = find(id)
      const option = entry.sample.recommended
      if (!option || option.option_id !== optionId) {
        return wait({ status: 'rejected', reason: 'This option has not been validated. Prepare it first.', confirmation: null, repeat: false })
      }
      if (entry.confirmation) {
        return wait({ status: 'confirmed', reason: null, confirmation: entry.confirmation, repeat: true })
      }
      entry.confirmation = {
        confirmation_id: `SIM-CONF-${id}-${optionId}`, simulated: true, data_source: 'mock',
        note: 'SIMULATED rebooking. No real airline ticket was created.', booking_id: id, option_id: optionId,
        additional_cost: option.additional_cost, currency: option.currency, updated_itinerary: option.flight_details,
      }
      entry.summary = { ...entry.summary, status: 'rebooked', rebooked: true }
      return wait({ status: 'confirmed', reason: null, confirmation: entry.confirmation, repeat: false })
    },
  }
}
