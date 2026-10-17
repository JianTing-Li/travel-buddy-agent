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


# --- the agent is told WHICH limit each removed option broke (PRD: explain which limits cannot be met) ---

def test_a_search_names_the_removed_options_and_the_limit_each_one_breaks():
    _, _, tools, _ = stack()
    out = tools["search_replacements"](booking_id=B, limits=limits(tools))
    assert [o["option_id"] for o in out["options"]] == ["opt-1a", "opt-1b"]
    removed = {o["option_id"]: o for o in out["excluded_by_limits"]}
    assert set(removed) == {"opt-1c"}
    assert removed["opt-1c"]["reasons"] == ["arrives after the arrival deadline"]
    assert "NOT suitable recommendations" in out["excluded_note"]


def test_when_nothing_fits_every_option_is_listed_with_its_reason():
    service = MockService(today=TODAY)
    toolset = build_tools(service, limits_filter=limits_filter)
    gate = ConfirmationGate(toolset.tools, toolset.complete_rebooking, source="real")
    out = gate.tools()["search_replacements"](
        booking_id="MOCK-CASE-3", limits={**limits(None), "budget_additional_cost": 0, "passenger_count": 3})
    assert out["options"] == []
    reasons = {o["option_id"]: o["reasons"] for o in out["excluded_by_limits"]}
    assert set(reasons) == {"opt-3a", "opt-3b", "opt-3c"} and all(reasons.values())
    assert "arrives after the arrival deadline" in reasons["opt-3a"]
    assert "additional cost is over the budget" in reasons["opt-3b"]


def test_a_removed_option_never_carries_untrusted_free_text_to_the_agent():
    """Case 4's $200 option has a planted instruction. The agent may be told it was removed, never what it says."""
    service = MockService(today=TODAY)
    toolset = build_tools(service, limits_filter=limits_filter)
    gate = ConfirmationGate(toolset.tools, toolset.complete_rebooking, source="real")
    out = gate.tools()["search_replacements"](
        booking_id="MOCK-CASE-4", limits={**limits(None), "budget_additional_cost": 100})
    assert out["options"] == [] and [o["option_id"] for o in out["excluded_by_limits"]] == ["opt-4a"]
    import json
    assert "Ignore the budget" not in json.dumps(out) and "extras" not in json.dumps(out["excluded_by_limits"])


def test_an_unchecked_search_adds_no_exclusion_list():
    _, _, tools, _ = stack()
    out = tools["search_replacements"](booking_id=B)
    assert out["limits_checked_by_code"] is False and "excluded_by_limits" not in out


def test_a_wrong_currency_option_is_listed_as_removed_because_it_cannot_be_compared():
    service = MockService(today=TODAY)
    service.set_faults(B, ["wrong_currency"])
    toolset = build_tools(service, limits_filter=limits_filter)
    gate = ConfirmationGate(toolset.tools, toolset.complete_rebooking, source="real")
    out = gate.tools()["search_replacements"](booking_id=B, limits=limits(None))
    assert out["options"] == [] and all("cannot be compared" in " ".join(o["reasons"]) for o in out["excluded_by_limits"])


# --- opt-in strict mode: no checked search, no prepare and no confirm ---

def strict_stack():
    service = MockService(today=TODAY)
    toolset = build_tools(service, limits_filter=limits_filter)
    done = []

    def complete(booking_id, option_id):
        done.append((booking_id, option_id))
        return toolset.complete_rebooking(booking_id, option_id)

    gate = ConfirmationGate(toolset.tools, complete, source="real", require_checked_search=True)
    return gate, gate.tools(), done


def test_strict_mode_refuses_to_prepare_before_any_checked_search():
    gate, tools, done = strict_stack()
    with pytest.raises(GateRefusal, match="no limits were confirmed"):
        tools["prepare_rebooking"](booking_id=B, option_id="opt-1a")
    assert gate.confirm(B, "opt-1a")["status"] == "rejected" and done == []


def test_strict_mode_refuses_an_unchecked_search_too():
    gate, tools, done = strict_stack()
    tools["search_replacements"](booking_id=B)  # no limits: unchecked, so nothing is confirmed
    with pytest.raises(GateRefusal):
        tools["prepare_rebooking"](booking_id=B, option_id="opt-1a")
    assert done == []


def test_strict_mode_works_normally_once_the_limits_were_checked():
    gate, tools, done = strict_stack()
    tools["search_replacements"](booking_id=B, limits=limits(tools))
    assert tools["prepare_rebooking"](booking_id=B, option_id="opt-1a")["validation_result"] == "valid"
    assert gate.confirm(B, "opt-1a")["status"] == "confirmed" and done == [(B, "opt-1a")]


def test_strict_mode_is_off_by_default():
    _, gate_default, _, _ = stack()
    assert gate_default.require_checked_search is False
