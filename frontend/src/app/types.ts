/**
 * API data types. Owner: Jian.
 *
 * Mirrors backend/app/contract/models.py (the contract) and backend/app/api/schemas.py (the HTTP API).
 * Field names match the backend exactly; a backend test compares them. Everything served today is simulated.
 * Fields typed loosely (string, Record) are TODOs in the contract: eligibility, validity, validation_result
 * and flight_details have no agreed allowed values yet.
 */

export type DataSource = "duffel" | "mock";

// --- contract models -----------------------------------------------------------------

export interface Limits {
  budget_additional_cost: number;
  arrival_window: string;
  max_connections: number;
  passenger_count: number;
}

/** Provisional keys the mock service puts in flight_details; real Duffel data may differ. */
export interface FlightDetails {
  airline?: string;
  flight?: string;
  origin?: string;
  destination?: string;
  /** ISO timestamp with the local UTC offset, e.g. 2026-10-15T11:00-04:00 */
  departs?: string;
  arrives?: string;
  duration?: string;
  connections?: number;
  simulated?: boolean;
  [key: string]: unknown;
}

export interface Option {
  option_id: string;
  flight_details: FlightDetails;
  eligibility: string;
  /** Additional cost for the whole booking, in `currency`. */
  additional_cost: number;
  currency: string;
  validity: string;
  data_source: DataSource;
}

export interface Passenger {
  [key: string]: unknown;
}

export interface TripContext {
  original_itinerary: Record<string, unknown>;
  passengers: Passenger[];
  disruption_details: Record<string, unknown>;
  data_source: DataSource;
}

export interface ValidationResult {
  latest_option_details: Option;
  validation_result: string;
  changes_to_review: string[];
}

export interface Handoff {
  case_id: string;
  booking_details: Record<string, unknown>;
  confirmed_needs: Limits;
  unresolved_issue: string;
}

// --- HTTP API --------------------------------------------------------------------------

/** Send as the X-Session-Id header on every call except POST /sessions and GET /health. */
export const SESSION_HEADER = "X-Session-Id";

export interface SessionCreate {
  /** Mock scenario names, e.g. ["case_1"]. Omit for all of them. */
  scenarios?: string[] | null;
}

export interface SessionOut {
  session_id: string;
  booking_ids: string[];
  simulated: true;
}

export interface BookingSummary {
  booking_id: string;
  origin: string;
  destination: string;
  departs: string;
  passenger_count: number;
  status: string;
  disruption_type: string;
  data_source: DataSource;
  rebooked: boolean;
}

export interface BookingDetail {
  summary: BookingSummary;
  trip: TripContext;
  confirmation: Confirmation | null;
}

/** Simulated confirmation returned after a rebooking is completed. */
export interface Confirmation {
  confirmation_id: string;
  simulated: true;
  data_source: DataSource;
  note: string;
  booking_id: string;
  option_id: string;
  additional_cost: number;
  currency: string;
  updated_itinerary: FlightDetails;
}

export interface ErrorOut {
  detail: string;
}

export interface ChatIn {
  booking_id: string;
  /** 1 to 2000 characters, not blank. */
  message: string;
}

export interface ConfirmCard {
  booking_id: string;
  option: Option;
  validation_result: string;
  changes_to_review: string[];
  simulated: true;
  notice: string;
}

export type StoppedReason = "reply" | "step_limit" | "error";

export interface ChatOut {
  reply: string;
  stopped_reason: StoppedReason;
  confirm_card: ConfirmCard | null;
}

export interface ConfirmIn {
  booking_id: string;
  option_id: string;
}

/** 200 confirmed (or a repeat of it), 202 pending, 409 rejected. */
export interface ConfirmOut {
  status: "confirmed" | "rejected" | "pending";
  reason: string | null;
  confirmation: Confirmation | null;
  repeat: boolean;
}

// --- UI only (not sent to the backend) ---------------------------------------------------

export interface ChatMessage {
  role: "traveler" | "assistant";
  text: string;
}

/**
 * The contract between the app shell and the chat component (features/chat, built separately).
 * The shell renders the chat and passes the booking; the chat sends messages through `onSend`
 * and shows whatever the shell gives back in `messages`.
 */
export interface ChatSlotProps {
  bookingId: string;
  messages: ChatMessage[];
  sending: boolean;
  onSend: (text: string) => void;
}
