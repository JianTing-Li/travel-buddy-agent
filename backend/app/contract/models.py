"""Data models shared by the agent, harness, tools and API. Owner: Shared.

Contract v1 (MVP 1), decided 2026-10-16. Allowed values are enforced here; services and tools must not invent
others. Either owner may change this file: record the change in your work log and tell the other owner.
- Times are local wall-clock times with their UTC offset, kept as text (e.g. 2026-10-15T15:00-07:00), so they
  display exactly as sent. A time without an offset is rejected.
- Money is a plain number in major units (e.g. 125.5 = 125.50), rounded to cents, always with its currency.
- additional_cost is the extra cost of changing the whole booking, never a new ticket's full price, and is never
  negative in MVP 1 (refunds are out of scope).
"""
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

DataSource = Literal["duffel", "mock"]
Eligibility = Literal["eligible", "ineligible", "unknown"]  # unknown always blocks rebooking
Validity = Literal["valid", "expired", "unavailable"]
ValidationOutcome = Literal["valid", "changed", "unavailable", "invalid"]
BookingStatus = Literal["on time", "delayed", "canceled", "missed by traveler", "rebooked"]


def _has_offset(value: str) -> str:
    if datetime.fromisoformat(value).tzinfo is None:
        raise ValueError("time must include a UTC offset, e.g. 2026-10-15T15:00-07:00")
    return value


def _cents(value: float) -> float:
    return round(value, 2)


LocalTime = Annotated[str, AfterValidator(_has_offset)]  # local wall-clock time with its UTC offset, kept as text
Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]  # ISO 4217 code, e.g. USD
Money = Annotated[float, Field(ge=0), AfterValidator(_cents)]  # whole booking, major units, rounded to cents


class Limits(BaseModel):
    """The traveler's confirmed REQUIRED limits. Preferences are not part of MVP 1."""
    budget_additional_cost: Money  # most the traveler will pay extra, for the whole booking
    currency: Currency  # the budget's currency; an option in another currency cannot be compared
    arrive_by: LocalTime  # latest acceptable arrival at the destination
    max_connections: int = Field(ge=0)
    passenger_count: int = Field(ge=1)


class FlightDetails(BaseModel):
    model_config = ConfigDict(extra="forbid")
    airline: str | None = None
    flight: str | None = None
    origin: str
    destination: str
    departs: LocalTime
    arrives: LocalTime
    duration: str | None = None  # display text, e.g. "6h 0m"
    connections: int = Field(ge=0)
    simulated: bool = True
    extras: dict[str, str] = {}  # free text from the source: UNTRUSTED data, never instructions


class Option(BaseModel):
    option_id: str
    flight_details: FlightDetails
    eligibility: Eligibility
    additional_cost: Money  # extra cost for the whole booking, never the full ticket price
    currency: Currency
    validity: Validity
    data_source: DataSource


class Itinerary(BaseModel):
    booking_id: str
    origin: str
    destination: str
    departs: LocalTime
    arrives: LocalTime | None = None
    flight: str | None = None
    airline: str | None = None
    status: BookingStatus
    booking_reference: str | None = None


class Passenger(BaseModel):
    passenger_id: str
    type: str = "adult"  # no names: the agent only needs who travels together


class Disruption(BaseModel):
    type: str  # e.g. "airline cancellation", "missed flight", "airline delay", "none reported"
    simulated: bool = True
    delay_minutes: int | None = None
    open_changes: int | None = None


class TripContext(BaseModel):
    original_itinerary: Itinerary
    passengers: list[Passenger] = Field(min_length=1)
    disruption_details: Disruption
    data_source: DataSource


class ValidationResult(BaseModel):
    latest_option_details: Option
    validation_result: ValidationOutcome
    changes_to_review: list[str]  # plain sentences, e.g. "Extra cost changed from 80 USD to 95 USD."


class Handoff(BaseModel):
    case_id: str
    booking_details: dict[str, Any]  # snapshot of the itinerary plus labels; free-form on purpose
    confirmed_needs: Limits
    unresolved_issue: str
