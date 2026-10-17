"""The confirmation gate holds prepare and confirm to the limits of the last checked search. Owner: Cheich."""
from datetime import date

import pytest

from backend.app.harness.confirmation import ConfirmationGate, GateRefusal
from backend.app.harness.limits import limits_filter
from backend.app.services.mock.mock_service import MockService
from backend.app.tools.registry import build_tools

TODAY = date(2026, 10, 15)
B = "MOCK-CASE-1"


def stack():
    service = MockService(today=TODAY)
    toolset = build_tools(service, limits_filter=limits_filter)
    done = []

    def complete(booking_id, option_id):
        done.append((booking_id, option_id))
        return toolset.complete_rebooking(booking_id, option_id)

    gate = ConfirmationGate(toolset.tools, complete, source="real")
    return service, gate, gate.tools(), done


def limits(tools, budget=0, arrive="15:00"):
    everything = build_tools(MockService(today=TODAY)).tools["search_replacements"](booking_id=B)
    day = everything["options"][0]["flight_details"]["arrives"][:10]
    return {"budget_additional_cost": budget, "currency": "USD", "arrive_by": f"{day}T{arrive}:00-07:00",
            "max_connections": 1, "passenger_count": 1}


def test_an_option_the_search_filtered_out_cannot_be_prepared_by_id():
    _, gate, tools, done = stack()
    tools["search_replacements"](booking_id=B, limits=limits(tools))
    with pytest.raises(GateRefusal, match="outside the traveler's confirmed limits"):
        tools["prepare_rebooking"](booking_id=B, option_id="opt-1c")  # the 4 PM option
    assert gate.confirm(B, "opt-1c")["status"] == "rejected" and done == []


def test_an_option_inside_the_limits_still_prepares_and_confirms():
    _, gate, tools, done = stack()
    tools["search_replacements"](booking_id=B, limits=limits(tools))
    assert tools["prepare_rebooking"](booking_id=B, option_id="opt-1a")["validation_result"] == "valid"
    assert gate.confirm(B, "opt-1a")["status"] == "confirmed" and done == [(B, "opt-1a")]


def test_an_option_that_drifts_outside_the_limits_before_confirm_is_rejected():
    service, gate, tools, done = stack()
    tools["search_replacements"](booking_id=B, limits=limits(tools))
    tools["prepare_rebooking"](booking_id=B, option_id="opt-1a")
    booking = service._bookings[B]
    booking.options["opt-1a"] = booking.options["opt-1a"].model_copy(update={"additional_cost": 80})  # now over $0
    out = gate.confirm(B, "opt-1a")
    assert out["status"] == "rejected" and "outside the traveler's confirmed limits" in out["reason"] and done == []


def test_new_approved_limits_replace_the_old_ones():
    _, gate, tools, _ = stack()
    tools["search_replacements"](booking_id=B, limits=limits(tools, budget=0, arrive="12:00"))
    with pytest.raises(GateRefusal):
        tools["prepare_rebooking"](booking_id=B, option_id="opt-1a")  # 2 PM is after a noon deadline
    tools["search_replacements"](booking_id=B, limits=limits(tools, budget=0, arrive="15:00"))
    assert tools["prepare_rebooking"](booking_id=B, option_id="opt-1a")["validation_result"] == "valid"


def test_a_refused_prepare_leaves_nothing_to_confirm():
    _, gate, tools, done = stack()
    tools["search_replacements"](booking_id=B, limits=limits(tools))
    tools["prepare_rebooking"](booking_id=B, option_id="opt-1a")
    with pytest.raises(GateRefusal):
        tools["prepare_rebooking"](booking_id=B, option_id="opt-1c")
    assert gate.confirm(B, "opt-1a")["status"] == "rejected" and done == []  # the earlier prepare was withdrawn too


def test_without_a_checked_search_the_gate_does_not_guess_limits():
    """No limits known means nothing to hold the option to. Callers that never search with limits are unchanged."""
    _, gate, tools, _ = stack()
    assert tools["prepare_rebooking"](booking_id=B, option_id="opt-1c")["validation_result"] == "valid"
    tools["search_replacements"](booking_id=B)  # no limits: unchecked, so nothing is remembered
    assert tools["prepare_rebooking"](booking_id=B, option_id="opt-1c")["validation_result"] == "valid"


def test_invalid_limits_are_not_remembered():
    _, gate, tools, _ = stack()
    tools["search_replacements"](booking_id=B, limits={"currency": "USD"})  # incomplete: filtered to nothing
    assert tools["prepare_rebooking"](booking_id=B, option_id="opt-1c")["validation_result"] == "valid"
