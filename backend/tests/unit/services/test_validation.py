"""Change descriptions travelers read when an option changed. Owner: Jian."""
from backend.app.contract.models import Option
from backend.app.services.validation import diff_options


def _option(departs: str, cost: float) -> Option:
    return Option(option_id="o1", eligibility="eligible", additional_cost=cost, currency="USD", validity="valid",
                  data_source="mock", flight_details={"origin": "JFK", "destination": "LAX", "departs": departs,
                                                      "arrives": "2026-10-17T14:00-07:00", "connections": 0})


def test_changes_are_plain_sentences_with_local_times_and_no_raw_timestamps():
    changes = diff_options(_option("2026-10-17T11:00-04:00", 0), _option("2026-10-17T12:30-04:00", 15))
    assert changes == ["Extra cost changed from 0 USD to 15 USD.",
                       "Departure time changed from 11:00 AM on Oct 17 to 12:30 PM on Oct 17."]
