"""Complete traveler limits for API tests, now that the live gate is strict. Owner: Jian.

The live app refuses to prepare or confirm an option until a search checked by code has confirmed the traveler's
limits. Tests that prepare an option first run such a search, with limits that the option fits exactly. The mock's
dates move with the calendar, so the limits are read from the option instead of being written by hand.
"""
from typing import Any, Callable

from backend.app.services.mock.scenarios import load_scenario


def limits_that_fit(option: dict[str, Any], passengers: int = 1) -> dict[str, Any]:
    """The tightest limits the option still meets: its own arrival, cost, currency and connections."""
    details = option["flight_details"]
    return {"budget_additional_cost": option["additional_cost"], "currency": option["currency"],
            "arrive_by": details["arrives"], "max_connections": details["connections"],
            "passenger_count": passengers}


def scenario_limits(scenario: str, option_id: str) -> dict[str, Any]:
    """Limits that fit one option of a mock scenario, for scripted model turns written before a session exists."""
    option = next(o for o in load_scenario(scenario).options if o.option_id == option_id)
    return limits_that_fit(option.model_dump(mode="json"))


def check_limits_for(tools: dict[str, Callable[..., Any]], booking_id: str, option_id: str) -> dict[str, Any]:
    """Run the checked search the strict gate needs before option_id can be prepared. Returns the checked result."""
    everything = tools["search_replacements"](booking_id=booking_id)["options"]
    option = next(o for o in everything if o["option_id"] == option_id)
    checked = tools["search_replacements"](booking_id=booking_id, limits=limits_that_fit(option))
    assert checked["limits_checked_by_code"] is True
    return checked
