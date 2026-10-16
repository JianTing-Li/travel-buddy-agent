"""Unit tests for the seeded mock booking generator and for adding bookings at runtime. Owner: Jian."""
import re
from datetime import date, datetime

import pytest

from backend.app.contract.models import Option, TripContext
from backend.app.services.mock.generator import GeneratorError, generate_scenario
from backend.app.services.mock.mock_service import MockService, MockServiceError

TODAY = date(2026, 10, 15)


def minutes(duration: str) -> int:
    hours, mins = re.fullmatch(r"(\d+)h (\d+)m", duration).groups()
    return int(hours) * 60 + int(mins)


def test_the_same_seed_gives_the_same_booking_and_other_seeds_differ():
    assert generate_scenario(7, TODAY) == generate_scenario(7, TODAY)
    assert generate_scenario(7, TODAY) != generate_scenario(8, TODAY)
    assert generate_scenario(7, TODAY).booking_id == "MOCK-GEN-7"


@pytest.mark.parametrize("seed", range(40))
def test_generated_bookings_are_valid_mock_data(seed):
    scenario = generate_scenario(seed, TODAY)
    trip = scenario.trip
    assert isinstance(trip, TripContext) and trip.data_source == "mock"
    itinerary = trip.original_itinerary
    assert itinerary.origin != itinerary.destination and itinerary.booking_id == scenario.booking_id
    assert itinerary.status in {"canceled", "missed by traveler"} and trip.disruption_details.simulated is True
    assert 2 <= len(scenario.options) <= 4
    assert len({o.option_id for o in scenario.options}) == len(scenario.options)
    for option in scenario.options:
        assert isinstance(option, Option) and option.data_source == "mock" and option.currency == "USD"
        assert option.additional_cost >= 0 and option.flight_details.simulated is True
        details = option.flight_details
        elapsed = datetime.fromisoformat(details.arrives) - datetime.fromisoformat(details.departs)
        assert elapsed.total_seconds() / 60 == minutes(details.duration)
        if scenario.passenger_count > 1:
            assert details.extras["cost_applies_to"] == f"all {scenario.passenger_count} travelers"


def test_passenger_list_matches_the_count():
    for seed in range(40):
        scenario = generate_scenario(seed, TODAY)
        assert len(scenario.trip.passengers) == scenario.passenger_count and 1 <= scenario.passenger_count <= 3


def test_a_named_case_is_reissued_under_a_new_booking_id():
    scenario = generate_scenario(3, TODAY, scenario="case_2")
    assert scenario.booking_id == "MOCK-CASE-2-G3" and scenario.trip.original_itinerary.booking_id == "MOCK-CASE-2-G3"
    assert [o.additional_cost for o in scenario.options] == [80, 140]  # the eval case's numbers are unchanged


@pytest.mark.parametrize("kwargs", [{"seed": -1}, {"seed": 1_000_000}, {"seed": 1, "scenario": "case_99"}])
def test_bad_seeds_and_scenarios_are_rejected(kwargs):
    with pytest.raises(GeneratorError):
        generate_scenario(today=TODAY, **kwargs)


def test_a_generated_booking_works_end_to_end_in_the_service():
    service = MockService(scenarios=["case_1"], today=TODAY)
    booking_id = service.add_booking(generate_scenario(5, TODAY))
    assert booking_id in service.booking_ids()
    option_id = service.search_replacements(booking_id)[0].option_id
    assert service.prepare_rebooking(booking_id, option_id).validation_result == "valid"
    assert service.complete_rebooking(booking_id, option_id)["simulated"] is True


def test_adding_the_same_booking_twice_is_refused():
    service = MockService(scenarios=["case_1"], today=TODAY)
    service.add_booking(generate_scenario(5, TODAY))
    with pytest.raises(MockServiceError, match="already exists"):
        service.add_booking(generate_scenario(5, TODAY))


def test_reset_drops_generated_bookings():
    service = MockService(scenarios=["case_1"], today=TODAY)
    service.add_booking(generate_scenario(5, TODAY))
    service.reset()
    assert service.booking_ids() == ["MOCK-CASE-1"]
