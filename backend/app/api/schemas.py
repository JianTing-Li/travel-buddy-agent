"""Request and response shapes of the HTTP API. Owner: Jian.

frontend/src/app/types.ts mirrors these. Everything served today is simulated mock data.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..contract.models import Option, TripContext


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
