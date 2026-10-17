"""Mock dates stay fresh: replacements are always in the future, a missed flight is in the past, and a flight that
already left can't be offered or booked. Owner: Jian."""
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from backend.app.services.mock.generator import generate_scenario
from backend.app.services.mock.mock_service import MockService
from backend.app.services.mock.scenarios import MIN_LEAD, load_scenario

NY = ZoneInfo("America/New_York")


def _first(scenario):
    return min(datetime.fromisoformat(o.flight_details.departs) for o in scenario.options)


@pytest.mark.parametrize("hour", [0, 5, 7, 12, 18, 23])
@pytest.mark.parametrize("name", ["case_1", "case_2", "case_3", "case_4"])
def test_every_case_offers_only_flights_that_have_not_left_at_any_time_of_day(name, hour):
    now = datetime(2026, 10, 17, hour, 30, tzinfo=NY)
    scenario = load_scenario(name, now=now)
    assert _first(scenario) >= now + MIN_LEAD
    departs = datetime.fromisoformat(scenario.trip.original_itinerary.departs)
    if scenario.trip.original_itinerary.status == "missed by traveler":
        assert departs < now  # a missed flight has already left


def test_the_case_keeps_its_clock_times_when_it_moves_to_the_next_day():
    early = load_scenario("case_1", now=datetime(2026, 10, 17, 3, 0, tzinfo=NY))
    late = load_scenario("case_1", now=datetime(2026, 10, 17, 20, 0, tzinfo=NY))
    for a, b in zip(early.options, late.options):
        moved = datetime.fromisoformat(b.flight_details.arrives) - datetime.fromisoformat(a.flight_details.arrives)
        assert moved == timedelta(days=1)  # same 2 PM and 4 PM arrivals, so the eval deadlines still hold


@pytest.mark.parametrize("situation", ["on time", "canceled", "delayed", "missed", "random"])
@pytest.mark.parametrize("hour", [2, 13, 22])
def test_generated_bookings_follow_the_same_rules(situation, hour):
    now = datetime(2026, 10, 17, hour, 0, tzinfo=NY)
    scenario = generate_scenario(17, situation=situation, now=now)
    assert _first(scenario) >= now + MIN_LEAD
    if scenario.trip.original_itinerary.status == "missed by traveler":
        assert datetime.fromisoformat(scenario.trip.original_itinerary.departs) < now


def test_a_fixed_day_keeps_fixed_dates_for_tests():
    assert load_scenario("case_1", today=date(2026, 10, 15)).options[0].flight_details.departs.startswith("2026-10-15")


def test_a_flight_that_already_left_is_unavailable_and_cannot_be_prepared():
    clock = datetime(2026, 10, 15, 7, 0, tzinfo=NY)  # after opt-1b (6:30 AM), before opt-1a (11:00 AM)
    service = MockService(scenarios=["case_1"], today=date(2026, 10, 15), now=lambda: clock)
    by_id = {o.option_id: o for o in service.search_replacements("MOCK-CASE-1")}
    assert by_id["opt-1b"].validity == "unavailable" and by_id["opt-1a"].validity == "valid"
    assert service.prepare_rebooking("MOCK-CASE-1", "opt-1b").validation_result != "valid"


def test_only_untouched_bookings_need_a_refresh():
    clock = [datetime(2026, 10, 15, 3, 0, tzinfo=NY)]
    service = MockService(scenarios=["case_1", "case_4"], today=date(2026, 10, 15), now=lambda: clock[0])
    assert not service.needs_refresh("MOCK-CASE-1")
    service.search_replacements("MOCK-CASE-4")  # in use
    clock[0] = datetime(2026, 10, 15, 22, 0, tzinfo=NY)  # every flight has left
    assert service.needs_refresh("MOCK-CASE-1") and not service.needs_refresh("MOCK-CASE-4")


def test_back_to_normal_puts_a_missed_flight_in_the_future():
    now = datetime.now(timezone.utc)
    service = MockService(scenarios=["case_2"])
    assert datetime.fromisoformat(service.get_trip_context("MOCK-CASE-2").original_itinerary.departs) < now
    trip = service.clear_disruption("MOCK-CASE-2", load_scenario("case_2"))
    assert trip.original_itinerary.status == "on time"
    assert datetime.fromisoformat(trip.original_itinerary.departs) > now
