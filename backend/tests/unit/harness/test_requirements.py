"""Unit tests for the required-limits check and its enforcement in the loop. Owner: Cheich."""
import json
from datetime import date

import pytest

from backend.app.agent.decide import ToolCall
from backend.app.agent.loop import _run_tool, run_turn
from backend.app.harness.limits import limits_filter
from backend.app.harness.requirements import REQUIRED, check_limits
from backend.app.services.mock.mock_service import MockService
from backend.app.tools.registry import build_tools
from backend.tests.unit.agent.test_loop import FakeClient, resp, text, tool

FULL = {"budget_additional_cost": 0, "currency": "USD", "arrive_by": "2026-10-15T15:00-07:00",
        "max_connections": 1, "passenger_count": 1}


def test_complete_valid_limits_pass():
    assert check_limits(FULL).ok


def test_a_zero_budget_and_zero_connections_are_real_answers_not_missing():
    assert check_limits({**FULL, "budget_additional_cost": 0, "max_connections": 0}).ok


@pytest.mark.parametrize("name", list(REQUIRED))
def test_each_missing_required_limit_is_named(name):
    limits = {k: v for k, v in FULL.items() if k != name}
    check = check_limits(limits)
    assert not check.ok and check.missing == [name] and name in check.message


def test_none_counts_as_missing():
    assert check_limits({**FULL, "arrive_by": None}).missing == ["arrive_by"]


@pytest.mark.parametrize("bad", [None, {}, "text", [], 5])
def test_no_limits_at_all_lists_everything(bad):
    check = check_limits(bad)
    assert not check.ok and check.missing == list(REQUIRED)


@pytest.mark.parametrize("change, field", [
    ({"arrive_by": "2026-10-15T15:00"}, "arrive_by"),
    ({"budget_additional_cost": -5}, "budget_additional_cost"),
    ({"currency": "usd"}, "currency"),
    ({"max_connections": -1}, "max_connections"),
    ({"passenger_count": 0}, "passenger_count"),
])
def test_invalid_values_are_named_not_called_missing(change, field):
    check = check_limits({**FULL, **change})
    assert not check.ok and check.missing == [] and field in check.invalid and field in check.message


def test_the_message_tells_the_agent_to_ask_and_never_to_guess():
    msg = check_limits({"currency": "USD"}).message
    assert "ask the traveler" in msg and "Never guess" in msg and "never assume a limit is flexible" in msg


# --- enforcement in the loop ---

def _tools():
    return build_tools(MockService(today=date(2026, 10, 15)), limits_filter=limits_filter).tools


def test_a_search_without_limits_is_refused_with_an_error_the_model_can_read():
    out = _run_tool(ToolCall("t1", "search_replacements", {"booking_id": "MOCK-CASE-1"}), _tools())
    assert out["is_error"] and "Missing:" in out["content"] and "arrive_by" in out["content"]


def test_a_search_with_wrong_keys_is_refused_like_the_live_model_once_did():
    wrong = {"origin": "JFK", "destination": "LAX", "latest_arrival_local": "15:00", "max_additional_cost": 0}
    out = _run_tool(ToolCall("t1", "search_replacements", {"booking_id": "MOCK-CASE-1", "limits": wrong}), _tools())
    assert out["is_error"] and "budget_additional_cost" in out["content"]


def test_a_search_with_complete_limits_goes_through_and_is_filtered():
    direct = build_tools(MockService(today=date(2026, 10, 15))).tools["search_replacements"](booking_id="MOCK-CASE-1")
    day = direct["options"][0]["flight_details"]["arrives"][:10]
    limits = {**FULL, "arrive_by": f"{day}T15:00-07:00"}
    out = _run_tool(ToolCall("t1", "search_replacements", {"booking_id": "MOCK-CASE-1", "limits": limits}), _tools())
    body = json.loads(out["content"])
    assert "is_error" not in out and body["tool_data"]["limits_checked_by_code"] is True


def test_other_tools_are_not_affected():
    out = _run_tool(ToolCall("t1", "get_trip_context", {"booking_id": "MOCK-CASE-1"}), _tools())
    assert "is_error" not in out


def test_the_turn_continues_after_a_refusal_so_the_agent_can_ask_the_traveler():
    client = FakeClient(
        resp(tool("search_replacements", {"booking_id": "MOCK-CASE-1", "limits": {"currency": "USD"}})),
        resp(text("When do you need to arrive?")),
    )
    tools = _tools()
    schemas = build_tools(MockService(today=date(2026, 10, 15))).schemas
    r = run_turn(client, "m", "sys", [], "find me a flight", tools, schemas)
    refusal = r.history[2]["content"][0]
    assert refusal["is_error"] and r.stopped_reason == "reply" and r.reply == "When do you need to arrive?"
