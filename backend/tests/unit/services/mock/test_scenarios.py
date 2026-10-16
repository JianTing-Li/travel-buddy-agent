"""Unit tests for the mock scenario loader and a cross-check against the PRD eval case files. Owner: Jian."""
import json
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from backend.app.contract.models import Option, TripContext
from backend.app.services.mock.scenarios import (
    SCENARIOS_DIR,
    ScenarioError,
    load_scenario,
    scenario_names,
)

EVAL_DIR = Path(__file__).resolve().parents[3] / "evals" / "cases"
TODAY = date(2026, 10, 15)
CASES = ["case_1", "case_2", "case_3", "case_4"]


def eval_case(case: str) -> dict:
    (path,) = EVAL_DIR.glob(f"{case}_*.json")
    return json.loads(path.read_text())


def local_hour(timestamp: str) -> float:
    moment = datetime.fromisoformat(timestamp)
    return moment.hour + moment.minute / 60


def duration_minutes(text: str) -> int:
    hours, minutes = re.fullmatch(r"(\d+)h (\d+)m", text).groups()
    return int(hours) * 60 + int(minutes)


def test_all_four_eval_scenarios_exist():
    assert scenario_names() == CASES


@pytest.mark.parametrize("name, booking_id, passengers", [
    ("case_1", "MOCK-CASE-1", 1), ("case_2", "MOCK-CASE-2", 1),
    ("case_3", "MOCK-CASE-3", 3), ("case_4", "MOCK-CASE-4", 1),
])
def test_scenarios_are_mock_tagged_contract_models(name, booking_id, passengers):
    scenario = load_scenario(name, today=TODAY)
    assert scenario.booking_id == booking_id
    assert isinstance(scenario.trip, TripContext) and scenario.trip.data_source == "mock"
    assert len(scenario.trip.passengers) == passengers
    assert scenario.trip.disruption_details.simulated is True
    assert scenario.options and all(isinstance(o, Option) for o in scenario.options)
    assert all(o.data_source == "mock" and o.flight_details.simulated is True for o in scenario.options)


@pytest.mark.parametrize("name", CASES)
def test_duration_matches_departure_and_arrival(name):
    for option in load_scenario(name, today=TODAY).options:
        details = option.flight_details
        elapsed = datetime.fromisoformat(details.arrives) - datetime.fromisoformat(details.departs)
        assert elapsed.total_seconds() / 60 == duration_minutes(details.duration), option.option_id


def test_dates_are_relative_to_today():
    first = load_scenario("case_3", today=date(2026, 10, 15))
    later = load_scenario("case_3", today=date(2026, 10, 20))
    assert first.trip.original_itinerary.departs.startswith("2026-10-16T08:00")  # "tomorrow"
    assert later.trip.original_itinerary.departs.startswith("2026-10-21T08:00")


def test_offsets_follow_daylight_saving():
    summer = load_scenario("case_1", today=date(2026, 10, 15)).options[0].flight_details
    winter = load_scenario("case_1", today=date(2026, 12, 1)).options[0].flight_details
    assert summer.departs.endswith("-04:00") and summer.arrives.endswith("-07:00")
    assert winter.departs.endswith("-05:00") and winter.arrives.endswith("-08:00")


@pytest.mark.parametrize("case", ["case_1", "case_2", "case_3"])
def test_arrival_times_and_costs_match_the_eval_file(case):
    expected = sorted(
        (int(re.match(r"(\d+) PM", r["arrives"]).group(1)) + 12, r["additional_cost"])
        for r in eval_case(case)["test_setup"]["mock_replacements"]
    )
    actual = sorted(
        (local_hour(o.flight_details.arrives), o.additional_cost)
        for o in load_scenario(case, today=TODAY).options
    )
    assert actual == expected


def test_case_1_connecting_option_is_the_one_arriving_at_1pm():
    options = {o.flight_details.arrives[11:16]: o for o in load_scenario("case_1", today=TODAY).options}
    assert options["13:00"].flight_details.connections == 1
    assert options["14:00"].flight_details.connections == 0
    assert options["16:00"].flight_details.connections == 0


def test_case_3_costs_are_for_the_whole_group():
    scenario = load_scenario("case_3", today=TODAY)
    assert scenario.passenger_count == 3
    assert all(o.flight_details.extras["cost_applies_to"] == "all three travelers" for o in scenario.options)


def test_case_4_carries_the_embedded_instruction_as_data():
    setup = eval_case("case_4")["test_setup"]["mock_result"]
    (option,) = load_scenario("case_4", today=TODAY).options
    assert option.additional_cost == setup["additional_cost"]
    assert option.flight_details.extras["note"] == setup["embedded_text"]


@pytest.mark.parametrize("name", CASES)
def test_default_status_values_are_the_provisional_ones(name):
    for option in load_scenario(name, today=TODAY).options:
        assert (option.eligibility, option.validity) == ("eligible", "valid")


def test_unknown_scenario_lists_the_choices():
    with pytest.raises(ScenarioError, match="case_1"):
        load_scenario("nope")


def write_scenario(directory: Path, name: str, **changes) -> None:
    data = json.loads((SCENARIOS_DIR / "case_2.json").read_text())
    data.update(changes)
    (directory / f"{name}.json").write_text(json.dumps(data))


@pytest.mark.parametrize("changes, message", [
    ({"scenario_id": "other"}, "scenario_id"),
    ({"passenger_count": 0}, "at least one passenger"),
    ({"unexpected_field": 1}, "invalid"),
])
def test_invalid_scenario_files_are_rejected(tmp_path, changes, message):
    write_scenario(tmp_path, "case_2", **changes)
    with pytest.raises(ScenarioError, match=message):
        load_scenario("case_2", directory=tmp_path)


def test_duplicate_option_ids_are_rejected(tmp_path):
    options = json.loads((SCENARIOS_DIR / "case_2.json").read_text())["options"]
    write_scenario(tmp_path, "case_2", options=[options[0], options[0]])
    with pytest.raises(ScenarioError, match="repeats an option_id"):
        load_scenario("case_2", directory=tmp_path)


def test_bad_time_zone_is_rejected(tmp_path):
    data = json.loads((SCENARIOS_DIR / "case_2.json").read_text())
    data["options"][0]["departs"]["tz"] = "Mars/Olympus"
    (tmp_path / "case_2.json").write_text(json.dumps(data))
    with pytest.raises(ScenarioError, match="Bad local time"):
        load_scenario("case_2", directory=tmp_path)


def test_malformed_json_is_rejected(tmp_path):
    (tmp_path / "case_2.json").write_text("{not json")
    with pytest.raises(ScenarioError, match="invalid"):
        load_scenario("case_2", directory=tmp_path)
