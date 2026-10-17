"""Unit tests for MockService: safety rules, simulated labels, and the prepare/complete flow. Owner: Jian."""
import threading
from datetime import date

import pytest

from backend.app.contract.models import Handoff, Limits, Option, TripContext, ValidationResult
from backend.app.services.mock import provisional
from backend.app.services.mock.mock_service import (
    AlreadyRebookedError,
    MockService,
    RebookingNotAllowedError,
    UnknownBookingError,
    UnknownOptionError,
)

TODAY = date(2026, 10, 15)
LIMITS = Limits(budget_additional_cost=100, currency="USD", arrive_by="2026-10-15T15:00-07:00", max_connections=1,
                passenger_count=1)


@pytest.fixture
def service() -> MockService:
    return MockService(today=TODAY)


def tamper(service: MockService, booking_id: str, option_id: str, **changes) -> None:
    """Change an option behind the service's back, as a real service would between two calls."""
    booking = service._bookings[booking_id]
    booking.options[option_id] = booking.options[option_id].model_copy(update=changes)


def test_trip_context_is_a_mock_contract_model(service):
    trip = service.get_trip_context("MOCK-CASE-3")
    assert isinstance(trip, TripContext) and trip.data_source == "mock"
    assert len(trip.passengers) == 3 and trip.disruption_details.simulated is True


@pytest.mark.parametrize("booking_id", ["ord_0000A1", "off_0000B2", "oco_0000C3", "aic_0000D4"])
def test_duffel_ids_are_rejected(service, booking_id):
    with pytest.raises(UnknownBookingError, match="Duffel"):
        service.get_trip_context(booking_id)
    with pytest.raises(UnknownBookingError, match="Duffel"):
        service.search_replacements(booking_id)


def test_unknown_booking_and_option(service):
    with pytest.raises(UnknownBookingError):
        service.get_trip_context("MOCK-NOPE")
    with pytest.raises(UnknownOptionError):
        service.prepare_rebooking("MOCK-CASE-1", "opt-9z")


def test_search_returns_every_option_unfiltered_and_as_copies(service):
    options = service.search_replacements("MOCK-CASE-1")
    assert [o.option_id for o in options] == ["opt-1a", "opt-1b", "opt-1c"]  # the 4 PM option is not filtered out
    assert all(isinstance(o, Option) and o.data_source == "mock" for o in options)
    options[0].additional_cost = 999  # changing the returned copy must not change the service
    assert service.search_replacements("MOCK-CASE-1")[0].additional_cost == 0


def test_prepare_a_valid_option(service):
    service.search_replacements("MOCK-CASE-2")
    result = service.prepare_rebooking("MOCK-CASE-2", "opt-2a")
    assert isinstance(result, ValidationResult)
    assert result.validation_result == provisional.RESULT_VALID and result.changes_to_review == []
    assert result.latest_option_details.additional_cost == 80


def test_prepare_reports_changed_details_once_then_accepts_the_new_version(service):
    service.search_replacements("MOCK-CASE-2")
    tamper(service, "MOCK-CASE-2", "opt-2a", additional_cost=95.0)
    changed = service.prepare_rebooking("MOCK-CASE-2", "opt-2a")
    assert changed.validation_result == provisional.RESULT_CHANGED
    assert changed.changes_to_review == ["Extra cost changed from 80 USD to 95 USD."]
    assert changed.latest_option_details.additional_cost == 95
    again = service.prepare_rebooking("MOCK-CASE-2", "opt-2a")  # the traveler has now seen the new version
    assert again.validation_result == provisional.RESULT_VALID


@pytest.mark.parametrize("changes, result", [
    ({"validity": provisional.VALIDITY_EXPIRED}, provisional.RESULT_UNAVAILABLE),
    ({"validity": provisional.VALIDITY_UNAVAILABLE}, provisional.RESULT_UNAVAILABLE),
    ({"eligibility": provisional.INELIGIBLE}, provisional.RESULT_INVALID),
    ({"eligibility": provisional.UNKNOWN}, provisional.RESULT_INVALID),
    ({"validity": "something-else"}, provisional.RESULT_INVALID),
])
def test_bad_options_block_prepare_and_complete(service, changes, result):
    tamper(service, "MOCK-CASE-1", "opt-1a", **changes)
    prepared = service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    assert prepared.validation_result == result and prepared.changes_to_review
    with pytest.raises(RebookingNotAllowedError):
        service.complete_rebooking("MOCK-CASE-1", "opt-1a")


def test_complete_requires_prepare_of_the_same_option(service):
    with pytest.raises(RebookingNotAllowedError, match="not prepared"):
        service.complete_rebooking("MOCK-CASE-1", "opt-1a")
    service.prepare_rebooking("MOCK-CASE-1", "opt-1b")
    with pytest.raises(RebookingNotAllowedError, match="not prepared"):
        service.complete_rebooking("MOCK-CASE-1", "opt-1a")  # a different option than the prepared one


def test_complete_refuses_when_the_option_changed_after_prepare(service):
    service.prepare_rebooking("MOCK-CASE-2", "opt-2b")
    tamper(service, "MOCK-CASE-2", "opt-2b", additional_cost=150.0)
    with pytest.raises(RebookingNotAllowedError, match="changed after it was prepared"):
        service.complete_rebooking("MOCK-CASE-2", "opt-2b")


def test_complete_returns_a_labeled_simulated_confirmation(service):
    service.search_replacements("MOCK-CASE-2")
    service.prepare_rebooking("MOCK-CASE-2", "opt-2b")
    confirmation = service.complete_rebooking("MOCK-CASE-2", "opt-2b")
    assert confirmation["confirmation_id"] == "SIM-CONF-MOCK-CASE-2-opt-2b"
    assert confirmation["simulated"] is True and confirmation["data_source"] == "mock"
    assert "No real airline ticket" in confirmation["note"]
    assert confirmation["additional_cost"] == 140 and confirmation["currency"] == "USD"
    assert confirmation["updated_itinerary"]["flight"] == "Mock Air 270"
    assert service.get_confirmation("MOCK-CASE-2") == confirmation


def test_a_booking_can_only_be_rebooked_once(service):
    service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    service.complete_rebooking("MOCK-CASE-1", "opt-1a")
    with pytest.raises(AlreadyRebookedError):
        service.complete_rebooking("MOCK-CASE-1", "opt-1a")
    with pytest.raises(AlreadyRebookedError):
        service.complete_rebooking("MOCK-CASE-1", "opt-1b")
    after = service.prepare_rebooking("MOCK-CASE-1", "opt-1b")
    assert after.validation_result == provisional.RESULT_INVALID
    assert "already rebooked" in after.changes_to_review[0]


def test_concurrent_completions_succeed_exactly_once(service):
    service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    outcomes: list[str] = []

    def attempt() -> None:
        try:
            service.complete_rebooking("MOCK-CASE-1", "opt-1a")
            outcomes.append("ok")
        except AlreadyRebookedError:
            outcomes.append("duplicate")

    threads = [threading.Thread(target=attempt) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["duplicate"] * 7 + ["ok"]


def test_escalation_is_a_labeled_simulated_handoff(service):
    handoff = service.escalate_to_support("MOCK-CASE-4", "No option fits the traveler's limits.", LIMITS)
    assert isinstance(handoff, Handoff) and handoff.case_id == "SIM-MOCK-CASE-4"
    assert handoff.booking_details["simulated"] is True and "SIMULATED" in handoff.booking_details["label"]
    assert handoff.booking_details["booking_id"] == "MOCK-CASE-4"
    assert handoff.confirmed_needs == LIMITS and handoff.unresolved_issue.startswith("No option")


def test_escalation_for_an_unknown_or_duffel_booking_fails(service):
    with pytest.raises(UnknownBookingError):
        service.escalate_to_support("ord_0000A1", "x", LIMITS)


def test_reset_discards_simulated_state(service):
    service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    service.complete_rebooking("MOCK-CASE-1", "opt-1a")
    tamper(service, "MOCK-CASE-2", "opt-2a", additional_cost=1.0)
    service.reset()
    assert service.get_confirmation("MOCK-CASE-1") is None
    assert service.search_replacements("MOCK-CASE-2")[0].additional_cost == 80


def test_only_requested_scenarios_are_loaded():
    small = MockService(scenarios=["case_2"], today=TODAY)
    assert small.booking_ids() == ["MOCK-CASE-2"]
