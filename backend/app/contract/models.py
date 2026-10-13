"""Data models shared by the agent, harness, tools and API. Owner: Shared.

DRAFT: both owners must review before use.
Fields come only from the PRD tools table. Unclear types are marked TODO.
"""
from typing import Literal

from pydantic import BaseModel

DataSource = Literal["duffel", "mock"]


class Limits(BaseModel):
    budget_additional_cost: float  # TODO: confirm numeric type and currency handling
    arrival_window: str  # TODO: define structure (deadline vs start/end, time zone)
    max_connections: int
    passenger_count: int


class Option(BaseModel):
    option_id: str
    flight_details: dict  # TODO: define structure (airline, times with time zones, duration, connections)
    eligibility: str  # TODO: define allowed values
    additional_cost: float  # TODO: confirm numeric type
    currency: str
    validity: str  # TODO: define (expiry timestamp or status?)
    data_source: DataSource


class TripContext(BaseModel):
    original_itinerary: dict  # TODO: define structure
    passengers: list[dict]  # TODO: define passenger fields
    disruption_details: dict  # TODO: define structure
    data_source: DataSource


class ValidationResult(BaseModel):
    latest_option_details: Option
    validation_result: str  # TODO: define allowed values
    changes_to_review: list[str]  # TODO: define structure of changes


class Handoff(BaseModel):
    case_id: str
    booking_details: dict  # TODO: define structure
    confirmed_needs: Limits  # TODO: may also include preferences
    unresolved_issue: str
