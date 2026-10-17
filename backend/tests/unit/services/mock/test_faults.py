"""Unit tests for the mock service's fault switches, which feed the harness's automated checks. Owner: Jian."""
from datetime import date

import pytest

from backend.app.services.mock import provisional
from backend.app.services.mock.mock_service import (
    FAULTS,
    CHANGED_DETAILS_EXTRA_COST,
    MockService,
    MockServiceError,
    RebookingNotAllowedError,
    SimulatedFailureError,
    UnknownBookingError,
)

TODAY = date(2026, 10, 15)


@pytest.fixture
def service() -> MockService:
    return MockService(today=TODAY)


def test_every_fault_has_a_test_below():
    assert set(FAULTS) == {"unknown_eligibility", "wrong_currency", "unavailable_option", "changed_details",
                           "tool_failure", "uncertain_completion"}


def test_set_and_clear_faults(service):
    assert service.get_faults("MOCK-CASE-1") == []
    assert service.set_faults("MOCK-CASE-1", ["wrong_currency", "tool_failure"]) == ["tool_failure", "wrong_currency"]
    assert service.get_faults("MOCK-CASE-2") == []  # per booking
    assert service.set_faults("MOCK-CASE-1", []) == []


@pytest.mark.parametrize("faults", [["nope"], ["tool_failure", "nope"]])
def test_unknown_faults_are_rejected_and_change_nothing(service, faults):
    with pytest.raises(MockServiceError, match="Unknown faults"):
        service.set_faults("MOCK-CASE-1", faults)
    assert service.get_faults("MOCK-CASE-1") == []


@pytest.mark.parametrize("booking_id", ["ord_0000A1", "MOCK-NOPE"])
def test_faults_cannot_target_duffel_or_unknown_bookings(service, booking_id):
    with pytest.raises(UnknownBookingError):
        service.set_faults(booking_id, ["tool_failure"])


def test_unknown_eligibility_blocks_prepare_and_complete(service):
    service.set_faults("MOCK-CASE-1", ["unknown_eligibility"])
    assert all(o.eligibility == provisional.UNKNOWN for o in service.search_replacements("MOCK-CASE-1"))
    result = service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    assert result.validation_result == provisional.RESULT_INVALID
    with pytest.raises(RebookingNotAllowedError):
        service.complete_rebooking("MOCK-CASE-1", "opt-1a")


def test_wrong_currency_is_reported_without_touching_the_amount(service):
    service.set_faults("MOCK-CASE-2", ["wrong_currency"])
    options = service.search_replacements("MOCK-CASE-2")
    assert {o.currency for o in options} == {"EUR"} and [o.additional_cost for o in options] == [80, 140]


def test_only_the_first_option_becomes_unavailable(service):
    service.set_faults("MOCK-CASE-1", ["unavailable_option"])
    first = service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    other = service.prepare_rebooking("MOCK-CASE-1", "opt-1b")
    assert first.validation_result == provisional.RESULT_UNAVAILABLE
    assert other.validation_result == provisional.RESULT_VALID


def test_changed_details_only_acts_after_the_traveler_has_seen_the_options(service):
    service.set_faults("MOCK-CASE-2", ["changed_details"])
    assert service.get_option("MOCK-CASE-2", "opt-2a").additional_cost == 80  # nothing searched yet
    service.search_replacements("MOCK-CASE-2")
    changed = service.prepare_rebooking("MOCK-CASE-2", "opt-2a")
    assert changed.validation_result == provisional.RESULT_CHANGED
    assert changed.latest_option_details.additional_cost == 80 + CHANGED_DETAILS_EXTRA_COST
    assert "Extra cost changed from 80 USD to 95 USD." in changed.changes_to_review
    with pytest.raises(RebookingNotAllowedError):
        service.complete_rebooking("MOCK-CASE-2", "opt-2a")  # the changed option needs a new review first
    assert service.prepare_rebooking("MOCK-CASE-2", "opt-2a").validation_result == provisional.RESULT_VALID


def test_tool_failure_breaks_search_until_cleared(service):
    service.set_faults("MOCK-CASE-1", ["tool_failure"])
    with pytest.raises(SimulatedFailureError, match="Simulated tool failure"):
        service.search_replacements("MOCK-CASE-1")
    service.set_faults("MOCK-CASE-1", [])
    assert len(service.search_replacements("MOCK-CASE-1")) == 3


def test_uncertain_completion_drops_once_and_books_nothing(service):
    service.set_faults("MOCK-CASE-1", ["uncertain_completion"])
    service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    with pytest.raises(RuntimeError, match="result of the rebooking is unknown"):
        service.complete_rebooking("MOCK-CASE-1", "opt-1a")
    assert service.get_confirmation("MOCK-CASE-1") is None
    assert service.complete_rebooking("MOCK-CASE-1", "opt-1a")["simulated"] is True  # the fault fires only once


def test_the_uncertain_error_is_not_a_service_error_so_callers_treat_it_as_unknown(service):
    service.set_faults("MOCK-CASE-1", ["uncertain_completion"])
    service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    with pytest.raises(RuntimeError) as exc:
        service.complete_rebooking("MOCK-CASE-1", "opt-1a")
    assert not isinstance(exc.value, MockServiceError)


def test_faults_never_change_the_stored_scenario(service):
    service.set_faults("MOCK-CASE-1", ["unknown_eligibility", "wrong_currency", "unavailable_option"])
    service.set_faults("MOCK-CASE-1", [])
    options = service.search_replacements("MOCK-CASE-1")
    assert {o.eligibility for o in options} == {"eligible"} and {o.currency for o in options} == {"USD"}
    assert {o.validity for o in options} == {"valid"}


def test_reset_clears_faults(service):
    service.set_faults("MOCK-CASE-1", ["tool_failure"])
    service.reset()
    assert service.get_faults("MOCK-CASE-1") == []
