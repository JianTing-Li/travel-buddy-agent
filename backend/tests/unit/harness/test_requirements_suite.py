"""The requirement-understanding scorer: the ideal agent passes, and every kind of mistake is caught. Owner: Cheich."""
import copy

import pytest

from backend.tests.evals import requirements_suite as rs
from backend.tests.evals import runner
from backend.tests.evals.recording import resp, text, tool

CASES = {c["id"]: c for c in rs.load_cases()}


def play_and_score(case_id, replies=None):
    case = CASES[case_id]
    return rs.score(case, rs.play_case(case, "scripted", replies=replies))


def searching_agent(**changes):
    """An agent that always searches on its first message, with the ideal limits changed by `changes`."""
    def replies(case, ctx, turn):
        limits = {**rs._ideal_limits(case, ctx), **changes}
        limits = {k: v for k, v in limits.items() if v is not ...}
        return [resp(tool("search_replacements", {"booking_id": ctx.booking_id, "limits": limits})),
                resp(text("Simulated options. Nothing is booked."))]
    return replies


def test_there_are_fifteen_cases_and_each_has_what_the_scorer_needs():
    assert len(CASES) == 15
    for case in CASES.values():
        assert {"booking_id", "followup_answer", "final_limits", "traveler_message"} <= set(case)
        assert set(case["final_limits"]) == {"budget_additional_cost", "currency", "arrive_by_local",
                                             "max_connections", "passenger_count"}


@pytest.mark.parametrize("case_id", list(CASES))
def test_the_ideal_agent_passes_every_case(case_id):
    result = play_and_score(case_id)
    assert result["passed"], result["problems"]


def test_a_wrong_budget_is_caught():
    result = play_and_score("req_3_prd_case_3", searching_agent(budget_additional_cost=150))
    assert not result["passed"] and any("budget_additional_cost" in p for p in result["problems"])


def test_using_dollars_for_a_euro_budget_is_caught():
    result = play_and_score("req_7_other_currency", searching_agent(currency="USD"))
    assert not result["passed"] and any("currency" in p for p in result["problems"])


def test_wrong_hour_and_wrong_offset_are_caught():
    def at(hhmm_offset):
        def replies(case, ctx, turn):
            limits = {**rs._ideal_limits(case, ctx), "arrive_by": f"{ctx.day}T{hhmm_offset}"}
            return [resp(tool("search_replacements", {"booking_id": ctx.booking_id, "limits": limits})),
                    resp(text("Simulated options."))]
        return replies
    assert any("arrive_by" in p for p in play_and_score("req_7_other_currency", at("17:00:00-07:00"))["problems"])
    assert any("arrive_by" in p for p in play_and_score("req_7_other_currency", at("16:00:00+01:00"))["problems"])
    assert play_and_score("req_7_other_currency", at("16:00:00-08:00"))["passed"]  # winter Pacific time is accepted


def test_searching_on_a_guess_when_a_clarification_is_needed_is_caught():
    result = play_and_score("req_1_prd_case_1", searching_agent())  # the deadline was never given
    assert not result["passed"] and any("searched on the first message" in p for p in result["problems"])


def test_never_searching_is_a_missed_requirement():
    def only_talks(case, ctx, turn):
        return [resp(text("Hello! This is simulated. Could you tell me more?"))]
    result = play_and_score("req_5_vague", only_talks)
    assert not result["passed"] and any("never searched" in p for p in result["problems"])


def test_an_incomplete_search_is_refused_by_the_requirement_check_and_scores_as_missed():
    result = play_and_score("req_4_long_paragraph", searching_agent(max_connections=...))
    assert not result["passed"] and any("never searched" in p for p in result["problems"])


def test_claiming_a_booking_while_gathering_requirements_is_caught():
    def books(case, ctx, turn):
        return [resp(text("Done, you're booked on the simulated 2 PM flight!"))]
    result = play_and_score("req_9_injection_in_traveler_message", books)
    assert not result["passed"] and any("booked or claimed" in p for p in result["problems"])


def test_preparing_a_rebooking_while_gathering_requirements_is_caught():
    def prepares(case, ctx, turn):
        return [resp(tool("search_replacements", {"booking_id": ctx.booking_id, "limits": rs._ideal_limits(case, ctx)})),
                resp(tool("prepare_rebooking", {"booking_id": ctx.booking_id, "option_id": "opt-1a"})),
                resp(text("Simulated. Please confirm."))]
    result = play_and_score("req_7_other_currency", prepares)
    assert not result["passed"] and any("prepared a rebooking" in p for p in result["problems"])


def test_the_report_says_below_target_when_more_than_one_in_ten_fail():
    results = [{"case": f"c{i}", "run": 1, "passed": i != 0, "problems": ["x"] if i == 0 else [], "asked_first": True,
                "turns": 2, "seconds": 0.1} for i in range(9)]
    report = rs.format_report(results, "scripted")
    assert "8 of 9" in report and "BELOW the target" in report
    results[0]["passed"] = True
    assert "MEETS the target" in rs.format_report(results, "scripted")


def test_the_command_line_runs_the_requirements_suite_and_saves_json(tmp_path, capsys):
    out = tmp_path / "req.json"
    code = runner.main(["--mode", "scripted", "--suite", "requirements", "--cases", "req_1_prd_case_1,req_7_other_currency",
                        "--out", str(out)])
    printed = capsys.readouterr().out
    assert code == 0 and "Requirement-understanding report" in printed and "MEETS the target" in printed and out.exists()


def test_an_unknown_requirement_case_is_refused(capsys):
    with pytest.raises(SystemExit):
        runner.main(["--mode", "scripted", "--suite", "requirements", "--cases", "nope"])
    assert "unknown case" in capsys.readouterr().err


def test_a_plain_request_for_missing_information_counts_as_asking():
    assert rs._asks("Please tell me when you need to land.") and rs._asks("Could you confirm the date")
    assert rs._asks("When must you arrive?") and not rs._asks("Here are your options.")


def test_case_3_does_not_demand_a_question_the_prd_never_asks_for_but_still_forbids_the_floated_budget():
    case = CASES["req_3_prd_case_3"]
    assert case["expected"]["must_ask_before_search"] == [] and case["final_limits"]["budget_additional_cost"] == 0
    assert not play_and_score("req_3_prd_case_3", searching_agent(budget_additional_cost=150))["passed"]
