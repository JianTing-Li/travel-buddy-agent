"""Unreadable options must fail closed in the limits filter, not crash. Owner: Cheich."""
from backend.app.contract.models import FlightDetails, Limits, Option
from backend.app.harness.limits import check_option, limits_filter

LIMITS = {"budget_additional_cost": 100, "currency": "USD", "arrive_by": "2026-10-15T15:00-07:00",
          "max_connections": 1, "passenger_count": 1}


def _good_option(**details):
    flight = dict(origin="JFK", destination="LAX", departs="2026-10-15T08:00-04:00",
                  arrives="2026-10-15T14:00-07:00", connections=0)
    flight.update(details)
    return Option.model_construct(  # model_construct skips validation, to simulate data that slipped through
        option_id="x", flight_details=FlightDetails.model_construct(**flight), eligibility="eligible",
        additional_cost=0, currency="USD", validity="valid", data_source="mock")


def test_an_arrival_time_without_a_utc_offset_is_removed():
    reasons = check_option(_good_option(arrives="2026-10-15T14:00"), Limits(**LIMITS))
    assert reasons and "could not be checked" in reasons[0]


def test_an_arrival_time_that_is_not_a_time_is_removed_not_a_crash():
    assert limits_filter([_good_option(arrives="soon")], LIMITS) == []


def test_a_good_option_built_the_same_way_is_kept_so_the_helper_is_sound():
    assert [o.option_id for o in limits_filter([_good_option()], LIMITS)] == ["x"]
