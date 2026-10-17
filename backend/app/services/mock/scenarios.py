"""Loads the MOCK scenario files in data/mock/scenarios/ into contract models. Owner: Jian.

Scenario times are local wall-clock times with a day offset from a base day, resolved to ISO timestamps with a
UTC offset when loaded. The base day is today at the departure airport, or a later day once today's first
replacement flight is about to leave, so the options are always in the future (see `base_day`). A missed flight
is always in the past. Everything produced here is simulated and
tagged data_source="mock". The contract models are used unchanged.
"""
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

from ...contract.models import Option, TripContext
from . import provisional

SCENARIOS_DIR = Path(__file__).resolve().parents[3] / "data" / "mock" / "scenarios"
# A replacement leaving sooner than this can't really be caught, so the data moves to the next day.
MIN_LEAD = timedelta(minutes=60)
MOCK_AIRLINE = "Mock Air"  # simulated data is marked by each option's simulated flag and data_source, not its name


class ScenarioError(Exception):
    """A scenario file is missing or invalid."""


class _LocalTime(BaseModel):
    model_config = ConfigDict(extra="forbid")
    day_offset: int
    time: str  # HH:MM, local to tz
    tz: str  # IANA name, e.g. America/New_York


class _Disruption(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    status: str


class _Itinerary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    flight: str
    origin: str
    destination: str
    departs: _LocalTime


class _OptionFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    option_id: str
    flight: str
    origin: str
    destination: str
    departs: _LocalTime
    arrives: _LocalTime
    duration: str
    connections: int
    additional_cost: float  # cost for the whole booking
    currency: str
    eligibility: str = provisional.ELIGIBLE
    validity: str = provisional.VALIDITY_VALID
    extra: dict[str, str] = {}  # free text from the source; becomes FlightDetails.extras (untrusted)


class _ScenarioFile(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    note: str | None = Field(default=None, alias="_note")
    scenario_id: str
    booking_id: str
    passenger_count: int
    disruption: _Disruption
    original_itinerary: _Itinerary
    options: list[_OptionFile]


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    booking_id: str
    passenger_count: int
    trip: TripContext
    options: list[Option]


def scenario_names(directory: Path = SCENARIOS_DIR) -> list[str]:
    return sorted(p.stem for p in directory.glob("*.json"))


def _moment(local: _LocalTime, today: date) -> datetime:
    try:
        zone = ZoneInfo(local.tz)
        hour, minute = (int(part) for part in local.time.split(":"))
        return datetime.combine(today + timedelta(days=local.day_offset), time(hour, minute), tzinfo=zone)
    except (ValueError, KeyError) as exc:  # ZoneInfoNotFoundError is a KeyError
        raise ScenarioError(f"Bad local time {local.model_dump()}: {exc}") from exc


def _resolve(local: _LocalTime, today: date) -> str:
    return _moment(local, today).isoformat(timespec="minutes")


def base_day(first_departure: Any, now: datetime, tz: str) -> date:
    """Today at the departure airport, or the next day on which the first replacement still leaves at least
    MIN_LEAD from now. `first_departure(day)` gives that flight's departure for a candidate day."""
    try:
        day = now.astimezone(ZoneInfo(tz)).date()
    except (ValueError, KeyError) as exc:  # ZoneInfoNotFoundError is a KeyError
        raise ScenarioError(f"Bad local time zone {tz!r}: {exc}") from exc
    for _ in range(3):
        if first_departure(day) >= now + MIN_LEAD:
            return day
        day += timedelta(days=1)
    return day


def load_scenario(name: str, today: date | None = None, directory: Path = SCENARIOS_DIR,
                  now: datetime | None = None) -> Scenario:
    """Load one scenario. `today` fixes the base day for tests; without it the base day follows `now` (default:
    the current time) so every replacement is still in the future."""
    path = directory / f"{name}.json"
    if not path.is_file():
        raise ScenarioError(f"Unknown scenario '{name}'. Choose from: {', '.join(scenario_names(directory))}")
    try:
        data = _ScenarioFile(**json.loads(path.read_text()))
    except (ValueError, TypeError) as exc:  # json errors and pydantic validation errors
        raise ScenarioError(f"Scenario file {path.name} is invalid: {exc}") from exc
    if data.scenario_id != name:
        raise ScenarioError(f"Scenario file {path.name} has scenario_id '{data.scenario_id}'")
    if data.passenger_count < 1:
        raise ScenarioError(f"Scenario '{name}' needs at least one passenger")
    ids = [o.option_id for o in data.options]
    if len(ids) != len(set(ids)):
        raise ScenarioError(f"Scenario '{name}' repeats an option_id")

    live = today is None  # a fixed `today` (tests) means fixed data: no moving to the next day
    now = now or datetime.now(timezone.utc)
    if live:
        first = data.options[0].departs if data.options else data.original_itinerary.departs
        today = base_day(lambda day: min((_moment(o.departs, day) for o in data.options),
                                         default=_moment(data.original_itinerary.departs, day)),
                         now, first.tz)
    itinerary = data.original_itinerary
    departs = _resolve(itinerary.departs, today)
    if live and data.disruption.status == "missed by traveler" and datetime.fromisoformat(departs) > now:
        departs = _resolve(itinerary.departs, today - timedelta(days=1))  # a missed flight has already left
    trip = TripContext(
        original_itinerary={
            "booking_id": data.booking_id,
            "flight": itinerary.flight,
            "origin": itinerary.origin,
            "destination": itinerary.destination,
            "departs": departs,
            "status": data.disruption.status,
        },
        passengers=[{"passenger_id": f"{data.booking_id}-P{i + 1}", "type": "adult"} for i in range(data.passenger_count)],
        disruption_details={"type": data.disruption.type, "simulated": True},
        data_source="mock",
    )
    options = [
        Option(
            option_id=o.option_id,
            flight_details={
                "airline": MOCK_AIRLINE,
                "flight": o.flight,
                "origin": o.origin,
                "destination": o.destination,
                "departs": _resolve(o.departs, today),
                "arrives": _resolve(o.arrives, today),
                "duration": o.duration,
                "connections": o.connections,
                "simulated": True,
                "extras": o.extra,
            },
            eligibility=o.eligibility,
            additional_cost=o.additional_cost,
            currency=o.currency,
            validity=o.validity,
            data_source="mock",
        )
        for o in data.options
    ]
    return Scenario(data.scenario_id, data.booking_id, data.passenger_count, trip, options)
