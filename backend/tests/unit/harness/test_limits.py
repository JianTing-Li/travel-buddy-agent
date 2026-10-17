"""Unit tests for the limits filter, including the PRD eval scenarios run through Jian's real tool. Owner: Cheich."""
import json
from datetime import date

import pytest

from backend.app.contract.models import Option
from backend.app.harness.limits import check_option, exclusion_reasons, limits_filter
from backend.app.services.mock.mock_service import MockService
from backend.app.tools.registry import build_tools

DEADLINE = "2026-10-15T15:00-07:00"
LIMITS = {"budget_additional_cost": 0, "currency": "USD", "arrive_by": DEADLINE, "max_connections": 1,
          "passenger_count": 1}


def opt(option_id="o", arrives="2026-10-15T14:00-07:00", cost=0, currency="USD", connections=0,
        eligibility="eligible", validity="valid"):
    return Option(
        option_id=option_id,
        flight_details={"origin": "JFK", "destination": "LAX", "departs": "2026-10-15T08:00-04:00",
                        "arrives": arrives, "connections": connections},
        eligibility=eligibility, additional_cost=cost, currency=currency, validity=validity, data_source="mock")


def kept(options, **limit_changes):
    return [o.option_id for o in limits_filter(options, {**LIMITS, **limit_changes})]


def test_an_option_inside_every_limit_is_kept():
    assert kept([opt("a")]) == ["a"]


def test_eval_case_1_the_4pm_option_is_removed():
    options = [opt("2pm", "2026-10-15T14:00-07:00"), opt("1pm", "2026-10-15T13:00-07:00", connections=1),
               opt("4pm", "2026-10-15T16:00-07:00")]
    assert kept(options) == ["2pm", "1pm"]


def test_arriving_exactly_at_the_deadline_is_allowed_and_one_minute_later_is_not():
    assert kept([opt("on", "2026-10-15T15:00-07:00")]) == ["on"]
    assert kept([opt("late", "2026-10-15T15:01-07:00")]) == []


def test_time_zones_are_compared_as_real_moments():
    assert kept([opt("early", "2026-10-15T17:00-04:00")]) == ["early"]  # 14:00 in LA
    assert kept([opt("late", "2026-10-15T18:30-04:00")]) == []          # 15:30 in LA


def test_cost_over_budget_is_removed_and_cost_equal_to_budget_is_kept():
    options = [opt("free", cost=0), opt("paid", cost=80)]
    assert kept(options) == ["free"]
    assert kept(options, budget_additional_cost=80) == ["free", "paid"]
    assert kept(options, budget_additional_cost=79.99) == ["free"]


def test_an_option_in_another_currency_is_removed_even_if_the_number_looks_cheap():
    assert kept([opt("eur", cost=10, currency="EUR")], budget_additional_cost=100) == []
    reasons = exclusion_reasons([opt("eur", cost=10, currency="EUR")], {**LIMITS, "budget_additional_cost": 100})
    assert "cannot be compared" in reasons["eur"][0]


def test_too_many_connections_are_removed():
    assert kept([opt("one", connections=1), opt("two", connections=2)]) == ["one"]
    assert kept([opt("one", connections=1)], max_connections=0) == []


@pytest.mark.parametrize("change", [{"eligibility": "unknown"}, {"eligibility": "ineligible"},
                                    {"validity": "expired"}, {"validity": "unavailable"}])
def test_unknown_ineligible_expired_and_unavailable_options_are_removed(change):
    assert kept([opt("x", **change)]) == []


@pytest.mark.parametrize("bad", [
    {}, {"budget_additional_cost": 0}, {**LIMITS, "arrive_by": "2026-10-15T15:00"},
    {**LIMITS, "budget_additional_cost": -1}, {**LIMITS, "currency": "usd"}, {**LIMITS, "max_connections": -1},
    {**LIMITS, "passenger_count": 0}, "not a dict", None,
])
def test_missing_or_invalid_limits_remove_every_option(bad):
    assert limits_filter([opt("a"), opt("b")], bad) == []
    assert set(exclusion_reasons([opt("a")], bad)) == {"a"}


def test_an_unreadable_option_is_removed_not_a_crash():
    assert limits_filter([opt("ok"), "garbage", None, {"option_id": "dict"}], LIMITS)[0].option_id == "ok"
    assert len(limits_filter([opt("ok"), "garbage", None], LIMITS)) == 1


def test_order_is_kept_and_an_empty_list_is_fine():
    assert kept([opt("b"), opt("a"), opt("c")]) == ["b", "a", "c"]
    assert limits_filter([], LIMITS) == []


def test_check_option_names_every_reason():
    from backend.app.contract.models import Limits
    reasons = check_option(opt("x", "2026-10-15T18:00-07:00", cost=500, connections=3, eligibility="unknown"),
                           Limits(**LIMITS))
    assert len(reasons) >= 4


# --- the PRD eval scenarios through Jian's real tool and mock data ---

@pytest.fixture
def search():
    toolset = build_tools(MockService(today=date(2026, 10, 15)), limits_filter=limits_filter)

    def run(booking_id, **limits):
        first = build_tools(MockService(today=date(2026, 10, 15))).tools["search_replacements"](booking_id=booking_id)
        day = first["options"][0]["flight_details"]["arrives"][:10]
        full = {"budget_additional_cost": 0, "currency": "USD", "arrive_by": f"{day}T15:00-07:00",
                "max_connections": 1, "passenger_count": 1, **limits}
        if "arrive_hour" in full:
            full["arrive_by"] = f"{day}T{full.pop('arrive_hour')}:00-07:00"
        return toolset.tools["search_replacements"](booking_id=booking_id, limits=full)
    return run


def ids(result):
    return [o["option_id"] for o in result["options"]]


def test_case_1_through_the_real_tool_drops_the_4pm_option(search):
    result = search("MOCK-CASE-1")
    assert result["limits_checked_by_code"] is True
    assert ids(result) == ["opt-1a", "opt-1b"]


def test_case_2_a_free_option_does_not_exist_so_a_zero_budget_returns_nothing(search):
    assert ids(search("MOCK-CASE-2", budget_additional_cost=0, arrive_hour="18")) == []
    assert ids(search("MOCK-CASE-2", budget_additional_cost=150, arrive_hour="18")) == ["opt-2a", "opt-2b"]


def test_case_3_nothing_fits_at_zero_then_only_the_120_option_at_150(search):
    assert ids(search("MOCK-CASE-3")) == []
    assert ids(search("MOCK-CASE-3", budget_additional_cost=150)) == ["opt-3b"]


def test_case_4_the_200_dollar_option_with_the_hidden_instruction_never_reaches_the_model(search):
    result = search("MOCK-CASE-4", budget_additional_cost=100)
    assert ids(result) == [] and "Ignore the budget" not in json.dumps(result)


def test_without_limits_the_tool_returns_everything_and_says_it_was_not_checked():
    toolset = build_tools(MockService(today=date(2026, 10, 15)), limits_filter=limits_filter)
    result = toolset.tools["search_replacements"](booking_id="MOCK-CASE-1")
    assert result["limits_checked_by_code"] is False and len(result["options"]) == 3
