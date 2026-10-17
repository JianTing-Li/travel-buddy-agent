"""Unit tests for the confirmation gate using the mock scenarios. Owner: Cheich."""
from backend.app.agent.tool_source import get_tool_source
from backend.app.harness.confirmation import ConfirmationGate

B, OPT = "MOCK-CASE-1", "opt-1a"


def make():
    src = get_tool_source("stub", "case_1")
    calls = []

    def complete(booking_id, option_id):
        calls.append((booking_id, option_id))
        return src.complete_rebooking(booking_id, option_id)

    gate = ConfirmationGate(src.tools, complete, "mock")
    return gate, gate.tools(), calls


def test_confirm_without_prepare_is_rejected():
    gate, _, calls = make()
    assert gate.confirm(B, OPT)["status"] == "rejected" and calls == []


def test_prepare_then_confirm_completes_once():
    gate, tools, calls = make()
    tools["prepare_rebooking"](B, OPT)
    out = gate.confirm(B, OPT)
    assert out["status"] == "confirmed" and out["result"]["simulated"] is True
    assert calls == [(B, OPT)]


def test_other_option_than_reviewed_is_rejected():
    gate, tools, calls = make()
    tools["prepare_rebooking"](B, OPT)
    assert gate.confirm(B, "opt-1b")["status"] == "rejected" and calls == []


def test_duplicate_confirm_does_not_complete_twice():
    gate, tools, calls = make()
    tools["prepare_rebooking"](B, OPT)
    gate.confirm(B, OPT)
    again = gate.confirm(B, OPT)
    assert again["repeat"] is True and calls == [(B, OPT)]


def test_changed_details_require_new_confirmation():
    gate, tools, calls = make()
    tools["prepare_rebooking"](B, OPT)
    gate._tools["prepare_rebooking"] = lambda booking_id, option_id: {
        "latest_option_details": {"option_id": OPT, "eligibility": "eligible", "additional_cost": 50, "currency": "USD", "data_source": "mock"},
        "validation_result": "valid", "changes_to_review": ["price changed"]}
    gate._prepare = gate._tools["prepare_rebooking"]
    assert gate.confirm(B, OPT)["status"] == "rejected" and calls == []
    gate._prepare = lambda booking_id, option_id: {
        "latest_option_details": {"option_id": OPT, "eligibility": "eligible", "additional_cost": 50, "currency": "USD", "data_source": "mock"},
        "validation_result": "valid", "changes_to_review": []}
    assert gate.confirm(B, OPT)["status"] == "confirmed"  # traveler saw the new details and confirmed again


def test_failure_marks_pending_and_is_not_retried():
    src = get_tool_source("stub", "case_1")
    n = []

    def boom(b, o):
        n.append(1)
        raise TimeoutError

    gate = ConfirmationGate(src.tools, boom, "mock")
    gate.tools()["prepare_rebooking"](B, OPT)
    assert gate.confirm(B, OPT)["status"] == "pending"
    assert gate.confirm(B, OPT)["repeat"] is True and len(n) == 1


def test_mock_completer_rejects_non_mock_option():
    src = get_tool_source("stub", "case_1")
    gate = ConfirmationGate(src.tools, src.complete_rebooking, "mock")
    gate._prepared[B] = (OPT, "x", "duffel")
    assert gate.confirm(B, OPT)["status"] == "rejected"


def _changed(cost, changes):
    return lambda booking_id, option_id: {
        "latest_option_details": {"option_id": OPT, "eligibility": "eligible", "additional_cost": cost,
                                  "currency": "USD", "data_source": "mock"},
        "validation_result": "valid", "changes_to_review": changes}


def test_rejection_says_what_changed():
    gate, tools, calls = make()
    tools["prepare_rebooking"](B, OPT)
    gate._prepare = _changed(50, ["additional cost changed from 0 to 50 USD"])
    out = gate.confirm(B, OPT)
    assert out["status"] == "rejected" and calls == []
    assert "What changed: additional cost changed from 0 to 50 USD." in out["reason"]


def test_rejection_without_change_list_has_no_empty_suffix():
    gate, tools, _ = make()
    tools["prepare_rebooking"](B, OPT)
    gate._prepare = _changed(50, [])
    assert "What changed" not in gate.confirm(B, OPT)["reason"]


def test_unavailable_option_rejection_includes_changes():
    gate, tools, _ = make()
    tools["prepare_rebooking"](B, OPT)
    gate._prepare = lambda booking_id, option_id: {
        "latest_option_details": {"option_id": OPT}, "validation_result": "unavailable",
        "changes_to_review": ["option is no longer available"]}
    out = gate.confirm(B, OPT)
    assert out["status"] == "rejected" and "no longer available" in out["reason"]


def test_a_recheck_that_blows_up_rejects_and_books_nothing():
    gate, tools, calls = make()
    tools["prepare_rebooking"](B, OPT)

    def broken(booking_id, option_id):
        raise TimeoutError("lost connection")

    gate._prepare = broken
    out = gate.confirm(B, OPT)
    assert out["status"] == "rejected" and "Could not re-check" in out["reason"] and calls == []
