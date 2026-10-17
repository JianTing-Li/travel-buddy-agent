"""The limits filter is really plugged into the live session tools (Jian's session builder). Owner: Cheich."""
from backend.app.api.sessions import _build
from backend.app.services.mock.scenarios import scenario_names


def _session_tools():
    return _build(scenario_names(), None).toolset.tools


def _limits_for(first_option_arrives: str, **changes):
    day = first_option_arrives[:10]
    return {"budget_additional_cost": 0, "currency": "USD", "arrive_by": f"{day}T15:00-07:00",
            "max_connections": 1, "passenger_count": 1, **changes}


def test_a_live_session_search_with_limits_is_checked_by_code_and_drops_the_4pm_option():
    search = _session_tools()["search_replacements"]
    everything = search(booking_id="MOCK-CASE-1")
    assert everything["limits_checked_by_code"] is False and len(everything["options"]) == 3
    limits = _limits_for(everything["options"][0]["flight_details"]["arrives"])
    checked = search(booking_id="MOCK-CASE-1", limits=limits)
    assert checked["limits_checked_by_code"] is True
    assert [o["option_id"] for o in checked["options"]] == ["opt-1a", "opt-1b"]


def test_a_live_session_search_with_a_wrong_currency_budget_returns_nothing():
    search = _session_tools()["search_replacements"]
    first = search(booking_id="MOCK-CASE-2")["options"][0]["flight_details"]["arrives"]
    in_eur = search(booking_id="MOCK-CASE-2", limits=_limits_for(first, currency="EUR", budget_additional_cost=500))
    assert in_eur["limits_checked_by_code"] is True and in_eur["options"] == []


def test_a_live_session_search_with_incomplete_limits_returns_nothing():
    result = _session_tools()["search_replacements"](booking_id="MOCK-CASE-1", limits={"currency": "USD"})
    assert result["limits_checked_by_code"] is True and result["options"] == []
