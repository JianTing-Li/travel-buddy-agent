"""Request and response shapes of the HTTP API. Owner: Jian.

frontend/src/app/types.ts mirrors these. Everything served today is simulated mock data.
"""
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

from ..contract.models import TripContext


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
