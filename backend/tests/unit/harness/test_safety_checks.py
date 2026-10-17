"""Automated safety checks: my guards, gate and loop against Jian's real mock service and its fault switches. Owner: Cheich.

No live model. Jian's own gate tests (tests/unit/tools/test_registry_with_gate.py) cover confirm without prepare,
repeats, a changed cost, access to another session's booking and a failure inside completion.
These cover the rest of the PRD list on the real mock output.
"""
import json
from datetime import date

import pytest

from backend.app.agent.decide import ToolCall
from backend.app.agent.loop import _run_tool, run_turn
from backend.app.harness.confirmation import ConfirmationGate
from backend.app.harness.guards import check_option_known
from backend.app.services.mock.mock_service import MockService
from backend.app.tools.registry import build_tools
from backend.tests.unit.agent.test_loop import FakeClient, resp, text, tool

TODAY = date(2026, 10, 15)
B, OPT = "MOCK-CASE-1", "opt-1a"
LIMITS = {"budget_additional_cost": 0, "currency": "USD", "arrive_by": "2026-10-15T15:00-07:00", "max_connections": 1, "passenger_count": 1}  # a search needs complete limits
ALL_OPTIONS = [
    ("MOCK-CASE-1", "opt-1a"), ("MOCK-CASE-1", "opt-1b"), ("MOCK-CASE-1", "opt-1c"),
    ("MOCK-CASE-2", "opt-2a"), ("MOCK-CASE-2", "opt-2b"),
    ("MOCK-CASE-3", "opt-3a"), ("MOCK-CASE-3", "opt-3b"), ("MOCK-CASE-3", "opt-3c"),
    ("MOCK-CASE-4", "opt-4a"),
]


def make(faults=None):
    service = MockService(today=TODAY)
    if faults:
        service.set_faults(B, faults)
    toolset = build_tools(service)
    completed = []

    def complete(booking_id, option_id):
        completed.append((booking_id, option_id))
        return toolset.complete_rebooking(booking_id, option_id)

    gate = ConfirmationGate(toolset.tools, complete, source="real")
    return toolset, gate, gate.tools(), completed


def prepare(tools, booking_id=B, option_id=OPT):
    tools["search_replacements"](booking_id=booking_id)
    return tools["prepare_rebooking"](booking_id=booking_id, option_id=option_id)


@pytest.mark.parametrize("booking_id, option_id", ALL_OPTIONS)
def test_guard_allows_every_normal_mock_option(booking_id, option_id):
    _, _, tools, _ = make()
    assert check_option_known(prepare(tools, booking_id, option_id)["latest_option_details"]).allowed


def test_unknown_eligibility_is_blocked_by_the_guard_and_the_gate():
    _, gate, tools, completed = make(["unknown_eligibility"])
    result = prepare(tools)
    assert not check_option_known(result["latest_option_details"]).allowed
    assert gate.confirm(B, OPT)["status"] == "rejected" and completed == []


def test_an_option_that_reports_unavailable_is_never_confirmed():
    _, gate, tools, completed = make(["unavailable_option"])
    assert prepare(tools)["validation_result"] != "valid"
    assert gate.confirm(B, OPT)["status"] == "rejected" and completed == []


def test_a_failing_search_tool_reaches_the_model_as_an_error_and_the_turn_continues():
    toolset, _, tools, _ = make(["tool_failure"])
    client = FakeClient(resp(tool("search_replacements", {"booking_id": B})), resp(text("I could not search.")))
    r = run_turn(client, "m", "sys", [], "find flights", tools, toolset.schemas)
    result = r.history[2]["content"][0]
    assert result["is_error"] and r.stopped_reason == "reply"


def test_case_4_injected_text_is_flagged_in_the_real_mock_data():
    toolset, _, tools, _ = make()
    out = _run_tool(ToolCall("t1", "search_replacements", {"booking_id": "MOCK-CASE-4", "limits": LIMITS}), tools)
    body = json.loads(out["content"])
    assert "tool_data" in body and "warning" in body
    assert any("note" in path for path in body["suspicious_fields"])


def test_normal_mock_data_is_not_flagged_as_suspicious():
    _, _, tools, _ = make()
    for booking in ("MOCK-CASE-1", "MOCK-CASE-2", "MOCK-CASE-3"):
        body = json.loads(_run_tool(ToolCall("t", "search_replacements", {"booking_id": booking, "limits": LIMITS}), tools)["content"])
        assert "warning" not in body


@pytest.mark.xfail(strict=True, reason=(
    "KNOWN GAP at the confirm step: the limits filter now removes wrong-currency options at SEARCH (see "
    "test_limits.py), but the confirmation gate itself does not compare an option's currency with the traveler's "
    "budget currency, so a wrong-currency option that reaches prepare and confirm is not blocked there."))
def test_a_wrong_currency_option_is_blocked():
    _, gate, tools, completed = make(["wrong_currency"])
    prepare(tools)
    assert gate.confirm(B, OPT)["status"] == "rejected" and completed == []
