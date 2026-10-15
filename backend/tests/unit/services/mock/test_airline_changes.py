"""Unit tests for simulated airline changes in the mock service. Owner: Jian."""
from datetime import date

import pytest

from backend.app.services.airline_change import AirlineChange
from backend.app.services.mock.mock_service import AlreadyRebookedError, MockService, UnknownBookingError

TODAY = date(2026, 10, 15)


@pytest.fixture
def service() -> MockService:
    return MockService(today=TODAY)


def test_a_booking_starts_with_no_changes(service):
    assert service.list_airline_changes("MOCK-CASE-1") == []


def test_a_delay_moves_the_departure_and_is_logged(service):
    change = service.add_airline_change("MOCK-CASE-3", "delay", delay_minutes=90)
    assert isinstance(change, AirlineChange)
    assert change.kind == "delay" and change.data_source == "mock" and change.simulated is True
    assert change.change_id == "SIM-CHG-MOCK-CASE-3-1"
    assert change.summary == "The airline delayed the departure by 90 minutes, to Oct 16, 9:30 AM (UTC-04:00)."
    trip = service.get_trip_context("MOCK-CASE-3")
    assert trip.original_itinerary["departs"] == "2026-10-16T09:30-04:00"  # was 08:00
    assert trip.original_itinerary["status"] == "delayed"
    assert trip.disruption_details == {"type": "airline delay", "simulated": True, "delay_minutes": 90}
    assert service.list_airline_changes("MOCK-CASE-3") == [change]


def test_delays_add_up_and_each_change_gets_its_own_id(service):
    first = service.add_airline_change("MOCK-CASE-1", "delay", delay_minutes=30)
    second = service.add_airline_change("MOCK-CASE-1", "delay", delay_minutes=45)
    assert [first.change_id, second.change_id] == ["SIM-CHG-MOCK-CASE-1-1", "SIM-CHG-MOCK-CASE-1-2"]
    assert service.get_trip_context("MOCK-CASE-1").disruption_details["delay_minutes"] == 75
    assert service.get_trip_context("MOCK-CASE-1").original_itinerary["departs"] == "2026-10-15T09:15-04:00"


def test_a_cancellation_marks_the_booking_canceled(service):
    change = service.add_airline_change("MOCK-CASE-2", "cancellation")
    assert change.kind == "cancellation"
    trip = service.get_trip_context("MOCK-CASE-2")  # started as a missed flight
    assert trip.original_itinerary["status"] == "canceled"
    assert trip.disruption_details["type"] == "airline cancellation"


@pytest.mark.parametrize("minutes", [0, -5])
def test_a_delay_needs_positive_minutes(service, minutes):
    with pytest.raises(ValueError):
        service.add_airline_change("MOCK-CASE-1", "delay", delay_minutes=minutes)
    assert service.list_airline_changes("MOCK-CASE-1") == []


def test_changes_do_not_leak_between_services_or_into_the_scenario_data():
    first, second = MockService(today=TODAY), MockService(today=TODAY)
    first.add_airline_change("MOCK-CASE-1", "cancellation")
    assert second.list_airline_changes("MOCK-CASE-1") == []
    assert second.get_trip_context("MOCK-CASE-1").original_itinerary["status"] == "canceled"  # case 1 starts canceled
    assert second.get_trip_context("MOCK-CASE-2").original_itinerary["status"] == "missed by traveler"


def test_returned_changes_and_trips_are_copies(service):
    service.add_airline_change("MOCK-CASE-1", "delay", delay_minutes=30)
    service.list_airline_changes("MOCK-CASE-1")[0].summary = "tampered"
    service.get_trip_context("MOCK-CASE-1").original_itinerary["status"] = "tampered"
    assert service.list_airline_changes("MOCK-CASE-1")[0].summary != "tampered"
    assert service.get_trip_context("MOCK-CASE-1").original_itinerary["status"] == "delayed"


def test_a_rebooked_booking_cannot_change_again(service):
    service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    service.complete_rebooking("MOCK-CASE-1", "opt-1a")
    with pytest.raises(AlreadyRebookedError):
        service.add_airline_change("MOCK-CASE-1", "delay", delay_minutes=30)


def test_reset_clears_changes_and_restores_the_itinerary(service):
    service.add_airline_change("MOCK-CASE-1", "delay", delay_minutes=30)
    service.reset()
    assert service.list_airline_changes("MOCK-CASE-1") == []
    assert service.get_trip_context("MOCK-CASE-1").original_itinerary["departs"] == "2026-10-15T08:00-04:00"


@pytest.mark.parametrize("booking_id", ["ord_0000A1", "MOCK-NOPE"])
def test_unknown_and_duffel_bookings_are_rejected(service, booking_id):
    with pytest.raises(UnknownBookingError):
        service.add_airline_change(booking_id, "cancellation")
    with pytest.raises(UnknownBookingError):
        service.list_airline_changes(booking_id)
