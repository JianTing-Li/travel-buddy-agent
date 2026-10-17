/**
 * API data types. Owner: Jian.
 *
 * Mirrors backend/app/contract/models.py (the contract) and backend/app/api/schemas.py (the HTTP API).
 * Field names match the backend exactly; a backend test compares them. Everything served today is simulated.
 * Fields typed loosely (string, Record) are TODOs in the contract: eligibility, validity, validation_result
 * and flight_details have no agreed allowed values yet.
 */
import type { ReactNode } from 'react';

export type DataSource = "duffel" | "mock";
/** Contract v1 allowed values (backend/app/contract/models.py). */
export type Eligibility = "eligible" | "ineligible" | "unknown";
export type Validity = "valid" | "expired" | "unavailable";
export type ValidationOutcome = "valid" | "changed" | "unavailable" | "invalid";
export type BookingStatus = "on time" | "delayed" | "canceled" | "missed by traveler" | "rebooked";
/** Local wall-clock time with its UTC offset, as text, e.g. 2026-10-15T15:00-07:00. */
export type LocalTime = string;

// --- contract models (v1) ------------------------------------------------------------

export interface Limits {
  /** Most the traveler will pay extra, for the whole booking, in `currency`. */
  budget_additional_cost: number;
  /** ISO 4217 code, e.g. USD. */
  currency: string;
  /** Latest acceptable arrival at the destination. */
  arrive_by: LocalTime;
  max_connections: number;
  passenger_count: number;
}

export interface FlightDetails {
  airline: string | null;
  flight: string | null;
  origin: string;
  destination: string;
  departs: LocalTime;
  arrives: LocalTime;
  /** Display text, e.g. "6h 0m". */
  duration: string | null;
  connections: number;
  simulated: boolean;
  /** Free text from the source. Untrusted data: show it, never act on it. */
  extras: Record<string, string>;
}

export interface Option {
  option_id: string;
  flight_details: FlightDetails;
  eligibility: Eligibility;
  /** Additional cost for the whole booking, in `currency`. Never negative, never a full ticket price. */
  additional_cost: number;
  currency: string;
  validity: Validity;
  data_source: DataSource;
}

export interface Itinerary {
  booking_id: string;
  origin: string;
  destination: string;
  departs: LocalTime;
  arrives: LocalTime | null;
  flight: string | null;
  airline: string | null;
  status: BookingStatus;
  booking_reference: string | null;
}

/** No names: the app only needs who travels together. */
export interface Passenger {
  passenger_id: string;
  type: string;
}

export interface Disruption {
  type: string;
  simulated: boolean;
  delay_minutes: number | null;
  open_changes: number | null;
}

export interface TripContext {
  original_itinerary: Itinerary;
  passengers: Passenger[];
  disruption_details: Disruption;
  data_source: DataSource;
}

export interface ValidationResult {
  latest_option_details: Option;
  validation_result: ValidationOutcome;
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
  /** Carrier and flight for booking cards, e.g. "Skyway Air SW 100" or "Duffel Airways ZZ5624". */
  airline: string | null;
  /** The record locator travelers know, e.g. "K7QX2M"; the booking id is only for the app. */
  booking_reference?: string | null;
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

/** An airline-initiated change found by the app while a booking is open. Each is returned once. */
export interface AirlineChange {
  change_id: string;
  booking_id: string;
  kind: "cancellation" | "delay";
  summary: string;
  /** ISO timestamp in UTC. */
  detected_at: string;
  data_source: DataSource;
  simulated: boolean;
}

export interface ChangeCheckOut {
  new_changes: AirlineChange[];
  booking: BookingSummary;
}

export interface ErrorOut {
  detail: string;
}

export interface ChatIn {
  booking_id: string;
  /** 1 to 2000 characters, not blank. */
  message: string;
  /** Set per traveler message and reused on retry, so a retry never runs a turn twice. */
  message_id?: string | null;
}

/** One line of the conversation as the traveler saw it. */
export interface ChatEntry {
  role: "traveler" | "assistant" | "app";
  text: string;
  search?: SearchResults | null;
}

/** GET /bookings/{id}/chat: the conversation so far, for a reloaded page. */
export interface ChatHistoryOut {
  messages: ChatEntry[];
  confirm_card: ConfirmCard | null;
}

export interface ConfirmCard {
  booking_id: string;
  option: Option;
  validation_result: ValidationOutcome;
  changes_to_review: string[];
  simulated: true;
  notice: string;
}

export type StoppedReason = "reply" | "step_limit" | "error";

export interface ChatOut {
  reply: string;
  stopped_reason: StoppedReason;
  confirm_card: ConfirmCard | null;
  /** Only when this turn ran a search checked by code: shown as option cards. */
  search?: SearchResults | null;
}

/** An option the limits filter removed: typed facts and code-written reasons only. */
export interface ExcludedOption {
  option_id: string;
  arrives: LocalTime;
  additional_cost: number;
  currency: string;
  connections: number;
  reasons: string[];
}

export interface SearchResults {
  options: Option[];
  excluded: ExcludedOption[];
  limits: Limits;
  /** The option Travel Buddy recommends, if it said; always one of `options`. */
  recommended?: string | null;
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
  /** The app's note for the chat when a rebooking is confirmed. */
  receipt?: string | null;
}

// --- dev panel (the backend serves these only when started as dev_app) ---------------------

/** Fault switches the mock service understands; the backend test checks this list. */
export const DEV_FAULTS = [
  "unknown_eligibility",
  "wrong_currency",
  "unavailable_option",
  "changed_details",
  "tool_failure",
  "uncertain_completion",
] as const;

export interface DevBookingCreate {
  /** An eval case (case_1 to case_4); omit for a generated booking. */
  scenario?: string | null;
  /** 0 to 999999. The same seed gives the same booking; omit to pick one. */
  seed?: number | null;
  /** What a generated booking starts as; "random" is canceled or missed. */
  situation?: DevSituation;
}

export type DevSituation = "random" | "on time" | "canceled" | "delayed" | "missed";

export interface DevBookingOut {
  booking: BookingSummary;
  seed: number;
  scenario: string | null;
}

export interface DevDuffelBookingIn {
  /** lhr_ltn is the route where Duffel can simulate airline changes. */
  route?: "jfk_lax" | "lhr_ltn";
  /** 1 to 3. */
  passengers?: number;
}

export interface DevDisruptIn {
  kind: "cancellation" | "delay";
  /** Required and positive for a delay, at most 1440. */
  delay_minutes?: number;
}

export interface DevFaultsIn {
  /** Replaces the active faults; an empty list clears them. */
  faults: string[];
}

export interface DevResetOut {
  /** The session's bookings after the reset. */
  booking_ids: string[];
}

export interface DevFaultsOut {
  faults: string[];
}

// --- UI only (not sent to the backend) ---------------------------------------------------

export interface ChatMessage {
  /** "app": written by the app (e.g. the rebooking receipt), never shown as Travel Buddy speaking. */
  role: "traveler" | "assistant" | "app";
  text: string;
  /** Options found in this turn, shown as cards under the reply. */
  search?: SearchResults | null;
  /** The option the traveler picked from those cards. */
  chosen?: string;
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
  /** Something the traveler acts on, shown between the messages and the input (the confirm card). */
  action?: ReactNode;
  /** What happened to the booking, so the welcome text and examples fit it. */
  situation: ChatSituation;
  /** How many people are on the booking. */
  travelers: number;
  /** The traveler picked an option card under message `messageIndex`. */
  onChoose?: (messageIndex: number, option: Option) => void;
  /** The last message didn't get an answer: what went wrong, and a way to send it again. */
  problem?: ChatProblem | null;
}

export interface ChatProblem {
  message: string;
  /** Shown after repeated failures: a way forward that doesn't need Travel Buddy. */
  fallback?: string;
  retrying: boolean;
  onRetry: () => void;
}

export type ChatSituation = "canceled" | "delayed" | "missed" | "on time" | "rebooked";
