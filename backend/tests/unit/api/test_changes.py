"""Unit tests for the airline-change check endpoint: shown-once tracking, notices and access. Owner: Jian."""
from datetime import date, timedelta
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from backend.app.api.main import create_app


class FakeModel:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.requests: list[dict] = []
        self.messages = NS(create=self._create)

    def _create(self, **kwargs):
        self.requests.append({"messages": [dict(m) for m in kwargs["messages"]]})
        return NS(content=[NS(type="text", text=self.replies.pop(0))], stop_reason="end_turn")


def start(model=None) -> tuple[TestClient, str]:
    client = TestClient(create_app(model_client=model, model="fake-model" if model else None))
    return client, client.post("/sessions").json()["session_id"]


def auth(session_id: str) -> dict[str, str]:
    return {"X-Session-Id": session_id}


def check(client, session_id, booking_id="MOCK-CASE-1"):
    return client.post(f"/bookings/{booking_id}/changes/check", headers=auth(session_id))


def service_of(client, session_id):
    return client.app.state.sessions.get(session_id).service


def test_no_changes_means_an_empty_list_and_the_current_booking():
    client, session_id = start()
    body = check(client, session_id).json()
    assert body["new_changes"] == [] and body["booking"]["booking_id"] == "MOCK-CASE-1"
    assert body["booking"]["status"] == "canceled"


def test_a_new_change_is_returned_once_and_updates_the_booking():
    client, session_id = start()
    service_of(client, session_id).add_airline_change("MOCK-CASE-3", "delay", delay_minutes=60)
    first = check(client, session_id, "MOCK-CASE-3").json()
    assert [c["change_id"] for c in first["new_changes"]] == ["SIM-CHG-MOCK-CASE-3-1"]
    change = first["new_changes"][0]
    assert change["kind"] == "delay" and change["data_source"] == "mock" and change["simulated"] is True
    tomorrow = (date.today() + timedelta(days=1)).isoformat()  # case 3 departs tomorrow at 08:00
    assert first["booking"]["status"] == "delayed" and first["booking"]["departs"].startswith(f"{tomorrow}T09:00")
    again = check(client, session_id, "MOCK-CASE-3").json()
    assert again["new_changes"] == [] and again["booking"]["status"] == "delayed"


def test_only_changes_after_the_last_check_are_new():
    client, session_id = start()
    service = service_of(client, session_id)
    service.add_airline_change("MOCK-CASE-1", "delay", delay_minutes=30)
    check(client, session_id)
    service.add_airline_change("MOCK-CASE-1", "delay", delay_minutes=15)
    second = check(client, session_id).json()
    assert [c["change_id"] for c in second["new_changes"]] == ["SIM-CHG-MOCK-CASE-1-2"]


def test_changes_are_tracked_per_booking():
    client, session_id = start()
    service_of(client, session_id).add_airline_change("MOCK-CASE-2", "cancellation")
    assert check(client, session_id, "MOCK-CASE-1").json()["new_changes"] == []
    assert len(check(client, session_id, "MOCK-CASE-2").json()["new_changes"]) == 1


def test_the_check_needs_a_session_and_an_owned_booking():
    client, session_id = start()
    assert client.post("/bookings/MOCK-CASE-1/changes/check").status_code == 401
    only_case_2 = client.post("/sessions", json={"scenarios": ["case_2"]}).json()["session_id"]
    other = check(client, only_case_2, "MOCK-CASE-1")
    assert other.status_code == 404 and other.json() == {"detail": "Booking not found."}
    assert check(client, session_id, "ord_0000A1").status_code == 404


def test_sessions_do_not_see_each_others_changes():
    client, first = start()
    second = client.post("/sessions").json()["session_id"]
    service_of(client, first).add_airline_change("MOCK-CASE-1", "cancellation")
    assert len(check(client, first).json()["new_changes"]) == 1
    assert check(client, second).json()["new_changes"] == []


def test_the_agent_hears_about_a_change_on_the_next_turn_only():
    model = FakeModel("Your flight was delayed. What do you need?", "ok")
    client, session_id = start(model)
    service_of(client, session_id).add_airline_change("MOCK-CASE-1", "delay", delay_minutes=45)
    check(client, session_id)
    check(client, session_id)  # a repeat check adds no second notice
    client.post("/chat", json={"booking_id": "MOCK-CASE-1", "message": "What happened?"}, headers=auth(session_id))
    first_user = model.requests[0]["messages"][-1]["content"]
    assert first_user.count("[App notice]") == 1 and "delayed the departure by 45 minutes" in first_user
    assert "get_trip_context" in first_user and first_user.endswith("What happened?")
    client.post("/chat", json={"booking_id": "MOCK-CASE-1", "message": "Thanks"}, headers=auth(session_id))
    assert model.requests[1]["messages"][-1]["content"] == "Thanks"


def test_check_logs_hold_no_booking_or_change_details(caplog):
    import logging
    client, session_id = start()
    service_of(client, session_id).add_airline_change("MOCK-CASE-1", "delay", delay_minutes=30)
    caplog.set_level(logging.INFO, logger="travel_buddy.api")
    check(client, session_id)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "route=/bookings/{booking_id}/changes/check" in text
    for secret in (session_id, "MOCK-CASE-1", "delayed", "SIM-CHG"):
        assert secret not in text
