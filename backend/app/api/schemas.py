"""Request and response shapes of the HTTP API. Owner: Jian.

frontend/src/app/types.ts mirrors these. Everything served today is simulated mock data.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..contract.models import Option, TripContext
from ..services.airline_change import AirlineChange


class SessionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenarios: list[str] | None = None  # mock scenario names; None means all of them


class SessionOut(BaseModel):
    session_id: str
    booking_ids: list[str]
    simulated: Literal[True] = True


class BookingSummary(BaseModel):
    booking_id: str
    origin: str
    destination: str
    departs: str  # ISO timestamp with UTC offset
    passenger_count: int
    status: str
    disruption_type: str
    data_source: Literal["duffel", "mock"]
    rebooked: bool
    airline: str | None = None  # the carrier or flight name shown on booking cards


class BookingDetail(BaseModel):
    summary: BookingSummary
    trip: TripContext
    confirmation: dict[str, Any] | None


class ErrorOut(BaseModel):
    detail: str


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_id: str = Field(min_length=1, max_length=64)
    message: str = Field(max_length=2000)

    @field_validator("message")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("message must not be blank")
        return value


class ConfirmCard(BaseModel):
    """The option the traveler is about to confirm, taken from the latest prepare_rebooking result."""
    booking_id: str
    option: Option
    validation_result: str
    changes_to_review: list[str]
    simulated: Literal[True] = True
    notice: str = "Simulated rebooking. No real ticket is issued."


class ChatOut(BaseModel):
    reply: str
    stopped_reason: Literal["reply", "step_limit", "error"]
    confirm_card: ConfirmCard | None


class ConfirmIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    booking_id: str = Field(min_length=1, max_length=64)
    option_id: str = Field(min_length=1, max_length=64)


class ConfirmOut(BaseModel):
    status: Literal["confirmed", "rejected", "pending"]
    reason: str | None = None
    confirmation: dict[str, Any] | None = None
    repeat: bool = False


class ChangeCheckOut(BaseModel):
    """Changes found since the last check (each is returned once), plus the booking as it is now."""
    new_changes: list[AirlineChange]
    booking: BookingSummary


# --- dev panel (only served when the app is created with dev=True) ---

class DevBookingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario: str | None = None  # an eval case name (case_1 to case_4); None for a random booking
    seed: int | None = Field(default=None, ge=0, le=999_999)  # None picks one; the same seed gives the same booking


class DevBookingOut(BaseModel):
    booking: BookingSummary
    seed: int
    scenario: str | None


class DevDuffelBookingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    route: Literal["jfk_lax", "lhr_ltn"] = "jfk_lax"  # lhr_ltn is the route where Duffel can simulate airline changes
    passengers: int = Field(default=1, ge=1, le=3)


class DevDisruptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["cancellation", "delay"]
    delay_minutes: int = Field(default=0, ge=0, le=1440)  # required (positive) for a delay


class DevFaultsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    faults: list[str]  # replaces the active faults; [] clears them


class DevFaultsOut(BaseModel):
    faults: list[str]


class DevResetOut(BaseModel):
    booking_ids: list[str]  # the session's bookings after the reset
