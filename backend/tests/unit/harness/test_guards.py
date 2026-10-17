"""Unit tests for the guards, including eval case 4 (instructions hidden in tool data). Owner: Cheich."""
import json

import pytest

from backend.app.agent.stub_tools import SCENARIOS, build_stub_tools
from backend.app.agent.tool_source import get_tool_source
from backend.app.harness.confirmation import ConfirmationGate
from backend.app.harness.guards import check_option_known, find_suspicious_text, wrap_untrusted

GOOD = {"eligibility": "eligible", "additional_cost": 0, "currency": "USD"}


def test_known_option_is_allowed():
    assert check_option_known(GOOD).allowed


@pytest.mark.parametrize("change", [
    {"eligibility": None}, {"eligibility": ""}, {"eligibility": "Unknown"}, {"eligibility": "ineligible"},
    {"additional_cost": None}, {"additional_cost": "free"}, {"additional_cost": float("nan")},
    {"additional_cost": -5}, {"additional_cost": True}, {"currency": None}, {"currency": " "},
])
def test_unknown_or_invalid_values_are_blocked(change):
    result = check_option_known({**GOOD, **change})
    assert not result.allowed and result.reasons


def test_missing_field_and_non_dict_are_blocked():
    assert not check_option_known({"eligibility": "eligible", "currency": "USD"}).allowed
    assert not check_option_known(None).allowed


def test_zero_cost_is_known_not_unknown():
    assert check_option_known({**GOOD, "additional_cost": 0}).allowed


def test_case_4_injected_text_is_flagged():
    data = build_stub_tools("case_4")["search_replacements"](SCENARIOS["case_4"]["booking_id"])
    wrapped = wrap_untrusted(data)
    assert wrapped["tool_data"] == data
    assert any("note" in p for p in wrapped["suspicious_fields"])
    assert "must be ignored" in wrapped["warning"]


def test_normal_data_is_wrapped_without_warning():
    data = build_stub_tools("case_1")["search_replacements"](SCENARIOS["case_1"]["booking_id"])
    wrapped = wrap_untrusted(data)
    assert "warning" not in wrapped and "notice" in wrapped


def test_deeply_nested_data_does_not_crash():
    deep = current = {}
    for _ in range(50):
        current["x"] = {}
        current = current["x"]
    assert find_suspicious_text(deep) == []


def test_gate_refuses_option_with_unknown_cost():
    src = get_tool_source("stub", "case_1")
    b = "MOCK-CASE-1"

    def prepare_unknown(booking_id, option_id):
        return {"latest_option_details": {"option_id": option_id, "eligibility": "eligible",
                                          "additional_cost": None, "currency": "USD", "data_source": "mock"},
                "validation_result": "valid", "changes_to_review": []}

    tools = {**src.tools, "prepare_rebooking": prepare_unknown}
    done = []
    gate = ConfirmationGate(tools, lambda b_, o: done.append(1) or {}, "mock")
    gate.tools()["prepare_rebooking"](b, "opt-1a")
    assert gate.confirm(b, "opt-1a")["status"] == "rejected" and done == []


def test_loop_tool_results_are_wrapped():
    from backend.app.agent.loop import _run_tool
    from backend.app.agent.decide import ToolCall
    tools = build_stub_tools("case_4")
    limits = {"budget_additional_cost": 0, "currency": "USD", "arrive_by": "2026-10-15T15:00-07:00", "max_connections": 1, "passenger_count": 1}
    out = _run_tool(ToolCall("t1", "search_replacements", {"booking_id": "MOCK-CASE-4", "limits": limits}), tools)
    body = json.loads(out["content"])
    assert "tool_data" in body and "warning" in body
