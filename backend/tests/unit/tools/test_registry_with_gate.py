"""Integration check: the registry tools driven through Cheich's real ConfirmationGate, no live model. Owner: Jian."""
from datetime import date

import pytest

from backend.app.harness.confirmation import ConfirmationGate
from backend.app.services.mock.mock_service import MockService
from backend.app.tools.registry import build_tools

TODAY = date(2026, 10, 15)
ALL_OPTIONS = [
    ("MOCK-CASE-1", "opt-1a"), ("MOCK-CASE-1", "opt-1b"), ("MOCK-CASE-1", "opt-1c"),
    ("MOCK-CASE-2", "opt-2a"), ("MOCK-CASE-2", "opt-2b"),
    ("MOCK-CASE-3", "opt-3a"), ("MOCK-CASE-3", "opt-3b"), ("MOCK-CASE-3", "opt-3c"),
    ("MOCK-CASE-4", "opt-4a"),
]


@pytest.fixture
def service() -> MockService:
    return MockService(today=TODAY)


@pytest.fixture
def stack(service):
    toolset = build_tools(service)
    gate = ConfirmationGate(toolset.tools, toolset.complete_rebooking, source="real")
    return service, gate.tools(), gate


def tamper(service: MockService, booking_id: str, option_id: str, **changes) -> None:
    booking = service._bookings[booking_id]
    booking.options[option_id] = booking.options[option_id].model_copy(update=changes)


@pytest.mark.parametrize("booking_id, option_id", ALL_OPTIONS)
def test_prepare_then_confirm_completes_a_simulated_rebooking(stack, booking_id, option_id):
    service, tools, gate = stack
    tools["search_replacements"](booking_id=booking_id)
    prepared = tools["prepare_rebooking"](booking_id=booking_id, option_id=option_id)
    assert prepared["validation_result"] == "valid"
    outcome = gate.confirm(booking_id, option_id)
    assert outcome["status"] == "confirmed"
    assert outcome["result"]["simulated"] is True and outcome["result"]["option_id"] == option_id
    assert service.get_confirmation(booking_id) == outcome["result"]


def test_confirm_without_prepare_is_rejected_and_nothing_is_booked(stack):
    service, _, gate = stack
    outcome = gate.confirm("MOCK-CASE-1", "opt-1a")
    assert outcome["status"] == "rejected"
    assert service.get_confirmation("MOCK-CASE-1") is None


def test_confirming_a_different_option_than_the_last_prepared_is_rejected(stack):
    service, tools, gate = stack
    tools["prepare_rebooking"](booking_id="MOCK-CASE-1", option_id="opt-1a")
    outcome = gate.confirm("MOCK-CASE-1", "opt-1b")
    assert outcome["status"] == "rejected"
    assert service.get_confirmation("MOCK-CASE-1") is None


def test_a_repeated_confirm_never_completes_twice(stack):
    service, tools, gate = stack
    tools["prepare_rebooking"](booking_id="MOCK-CASE-2", option_id="opt-2a")
    first = gate.confirm("MOCK-CASE-2", "opt-2a")
    second = gate.confirm("MOCK-CASE-2", "opt-2a")
    assert first["status"] == "confirmed" and second["repeat"] is True
    assert second["result"] == first["result"]


def test_a_changed_cost_blocks_the_confirm_until_the_new_version_is_prepared_again(stack):
    service, tools, gate = stack
    tools["search_replacements"](booking_id="MOCK-CASE-2")
    tools["prepare_rebooking"](booking_id="MOCK-CASE-2", option_id="opt-2a")
    tamper(service, "MOCK-CASE-2", "opt-2a", additional_cost=95.0)

    blocked = gate.confirm("MOCK-CASE-2", "opt-2a")
    assert blocked["status"] == "rejected"
    assert service.get_confirmation("MOCK-CASE-2") is None

    # The traveler must review the new version and confirm again.
    refreshed = tools["prepare_rebooking"](booking_id="MOCK-CASE-2", option_id="opt-2a")
    assert refreshed["latest_option_details"]["additional_cost"] == 95
    outcome = gate.confirm("MOCK-CASE-2", "opt-2a")
    assert outcome["status"] == "confirmed" and outcome["result"]["additional_cost"] == 95


def test_an_option_that_becomes_unavailable_is_rejected(stack):
    service, tools, gate = stack
    tools["prepare_rebooking"](booking_id="MOCK-CASE-1", option_id="opt-1a")
    tamper(service, "MOCK-CASE-1", "opt-1a", validity="unavailable")
    assert gate.confirm("MOCK-CASE-1", "opt-1a")["status"] == "rejected"
    assert service.get_confirmation("MOCK-CASE-1") is None


def test_unknown_eligibility_blocks_prepare_and_confirm(stack):
    service, tools, gate = stack
    tamper(service, "MOCK-CASE-1", "opt-1a", eligibility="unknown")
    prepared = tools["prepare_rebooking"](booking_id="MOCK-CASE-1", option_id="opt-1a")
    assert prepared["validation_result"] == "invalid"
    assert gate.confirm("MOCK-CASE-1", "opt-1a")["status"] == "rejected"
    assert service.get_confirmation("MOCK-CASE-1") is None


def test_a_booking_rebooked_elsewhere_is_rejected_not_reported_pending(stack):
    service, tools, gate = stack
    tools["prepare_rebooking"](booking_id="MOCK-CASE-1", option_id="opt-1a")
    service.complete_rebooking("MOCK-CASE-1", "opt-1a")  # completed outside the gate
    outcome = gate.confirm("MOCK-CASE-1", "opt-1a")
    assert outcome["status"] == "rejected"  # the gate's re-check catches it before completion


def test_a_failure_inside_completion_is_reported_pending_and_not_retried(service):
    toolset = build_tools(service)
    calls = []

    def failing_complete(booking_id, option_id):
        calls.append((booking_id, option_id))
        raise RuntimeError("connection dropped")

    gate = ConfirmationGate(toolset.tools, failing_complete, source="real")
    gate.tools()["prepare_rebooking"](booking_id="MOCK-CASE-1", option_id="opt-1a")
    first = gate.confirm("MOCK-CASE-1", "opt-1a")
    second = gate.confirm("MOCK-CASE-1", "opt-1a")
    assert first["status"] == "pending" and "Do not retry" in first["reason"]
    assert second["repeat"] is True and len(calls) == 1


def test_a_session_cannot_confirm_a_booking_it_does_not_own(service):
    toolset = build_tools(service, allowed_booking_ids={"MOCK-CASE-1"})
    gate = ConfirmationGate(toolset.tools, toolset.complete_rebooking, source="real")
    with pytest.raises(Exception, match="not available in this session"):
        gate.tools()["prepare_rebooking"](booking_id="MOCK-CASE-2", option_id="opt-2a")
    assert gate.confirm("MOCK-CASE-2", "opt-2a")["status"] == "rejected"
    assert service.get_confirmation("MOCK-CASE-2") is None
