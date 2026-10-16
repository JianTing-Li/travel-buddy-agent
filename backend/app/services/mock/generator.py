"""Seeded generator for MOCK test bookings. Owner: Jian.

The same seed always gives the same booking, so any run can be reproduced. Pass a scenario name (case_1 to case_4)
to get that eval case under a new booking id, or none for a random booking. Everything is simulated: flights are
invented, costs are for the whole booking, and no data is sent anywhere.

Random bookings get 3 to 5 options chosen to make real trade-offs: one costs nothing extra but leaves later,
earlier flights cost more (the earliest is always a paid nonstop), and one option has a connection.
"""
import random
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from ...contract.models import Option, TripContext
from . import provisional
from .scenarios import MOCK_AIRLINE, Scenario, load_scenario

AIRPORT_ZONES = {
    "JFK": "America/New_York", "BOS": "America/New_York", "MIA": "America/New_York",
    "ORD": "America/Chicago", "DEN": "America/Denver",
    "LAX": "America/Los_Angeles", "SFO": "America/Los_Angeles", "SEA": "America/Los_Angeles",
}
DISRUPTIONS = (("airline cancellation", "canceled"), ("missed flight", "missed by traveler"))
PAID_COSTS = (45, 60, 80, 95, 120, 140, 150, 175, 200)  # whole-booking additional costs, in USD
CONNECTION_EXTRA_MINUTES = 90
MAX_SEED = 999_999


class GeneratorError(ValueError):
    pass


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="minutes")


def _duration(minutes: int) -> str:
    return f"{minutes // 60}h {minutes % 60}m"


def _renamed(base: Scenario, booking_id: str, seed: int) -> Scenario:
    """The same scenario under a new booking id, so several copies can live in one session."""
    trip = base.trip.model_copy(deep=True)
    trip.original_itinerary.booking_id = booking_id
    return Scenario(f"{base.scenario_id}-g{seed}", booking_id, base.passenger_count, trip, base.options)


def generate_scenario(seed: int, today: date | None = None, scenario: str | None = None) -> Scenario:
    """Build a mock booking. `scenario` re-issues one of the eval cases; otherwise the seed decides everything."""
    if not 0 <= seed <= MAX_SEED:
        raise GeneratorError(f"seed must be between 0 and {MAX_SEED}")
    today = today or date.today()
    if scenario is not None:
        try:
            base = load_scenario(scenario, today=today)
        except Exception as exc:  # ScenarioError for an unknown name
            raise GeneratorError(str(exc)) from None
        return _renamed(base, f"{base.booking_id}-G{seed}", seed)

    rng = random.Random(seed)
    origin, destination = rng.sample(sorted(AIRPORT_ZONES), 2)
    origin_zone, destination_zone = ZoneInfo(AIRPORT_ZONES[origin]), ZoneInfo(AIRPORT_ZONES[destination])
    passengers = rng.randint(1, 3)
    disruption, status = rng.choice(DISRUPTIONS)
    day = today + timedelta(days=rng.randint(0, 1))
    booking_id = f"MOCK-GEN-{seed}"
    departs = datetime.combine(day, time(rng.randint(6, 9), 0), tzinfo=origin_zone)

    count = rng.randint(3, 5)
    hours = sorted(rng.sample(range(7, 21), count))  # distinct departure hours, earliest first
    free = rng.randrange(count // 2, count)  # the $0 option leaves in the later half, so paying more buys earlier
    connecting = rng.choice([i for i in range(1, count) if i != free])  # never the earliest flight
    paid = iter(sorted(rng.sample(PAID_COSTS, count - 1), reverse=True))  # earlier flights cost more
    block = rng.randrange(180, 360, 15)  # flying time for this route
    options = []
    for index, hour in enumerate(hours, start=1):
        position = index - 1
        leaves = datetime.combine(day, time(hour, rng.choice((0, 15))), tzinfo=origin_zone)
        connections = 1 if position == connecting else 0
        minutes = block + (CONNECTION_EXTRA_MINUTES if connections else 0)
        arrives = (leaves + timedelta(minutes=minutes)).astimezone(destination_zone)
        cost = 0.0 if position == free else float(next(paid))
        details = {
            "airline": MOCK_AIRLINE, "flight": f"Mock Air {rng.randint(200, 899)}", "origin": origin,
            "destination": destination, "departs": _iso(leaves), "arrives": _iso(arrives),
            "duration": _duration(minutes), "connections": connections, "simulated": True,
        }
        if passengers > 1:
            details["extras"] = {"cost_applies_to": f"all {passengers} travelers"}
        options.append(Option(
            option_id=f"opt-g{index}", flight_details=details, eligibility=provisional.ELIGIBLE,
            additional_cost=cost, currency="USD", validity=provisional.VALIDITY_VALID,
            data_source="mock",
        ))

    trip = TripContext(
        original_itinerary={
            "booking_id": booking_id, "flight": f"Mock Air {rng.randint(100, 199)}", "origin": origin,
            "destination": destination, "departs": _iso(departs), "status": status,
        },
        passengers=[{"passenger_id": f"{booking_id}-P{i + 1}", "type": "adult"} for i in range(passengers)],
        disruption_details={"type": disruption, "simulated": True},
        data_source="mock",
    )
    return Scenario(f"gen-{seed}", booking_id, passengers, trip, options)
