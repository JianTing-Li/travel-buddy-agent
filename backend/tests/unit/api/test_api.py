"""Unit tests for the API skeleton: sessions, booking access, isolation, redacted logging and CORS. Owner: Jian."""
import logging

import pytest
from fastapi.testclient import TestClient

from backend.app.api.main import create_app
from backend.app.api.sessions import SessionStore


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def new_session(client: TestClient, scenarios: list[str] | None = None) -> str:
    response = client.post("/sessions", json={"scenarios": scenarios} if scenarios else None)
    assert response.status_code == 201
    return response.json()["session_id"]


def auth(session_id: str) -> dict[str, str]:
    return {"X-Session-Id": session_id}


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_a_new_session_owns_all_mock_bookings_by_default(client):
    body = client.post("/sessions").json()
    assert body["booking_ids"] == ["MOCK-CASE-1", "MOCK-CASE-2", "MOCK-CASE-3", "MOCK-CASE-4"]
    assert body["simulated"] is True
    assert len(body["session_id"]) >= 40


def test_a_session_can_be_limited_to_some_scenarios(client):
    body = client.post("/sessions", json={"scenarios": ["case_2"]}).json()
    assert body["booking_ids"] == ["MOCK-CASE-2"]


@pytest.mark.parametrize("payload", [{"scenarios": ["case_99"]}, {"scenarios": []}, {"unexpected": 1}])
def test_bad_session_requests_are_rejected(client, payload):
    assert client.post("/sessions", json=payload).status_code == 422


@pytest.mark.parametrize("path", ["/bookings", "/bookings/MOCK-CASE-1"])
@pytest.mark.parametrize("headers", [{}, {"X-Session-Id": "not-a-real-session"}])
def test_calls_without_a_valid_session_get_401(client, path, headers):
    response = client.get(path, headers=headers)
    assert response.status_code == 401
    assert "Session not found" in response.json()["detail"]


def test_bookings_list_has_summaries(client):
    session_id = new_session(client)
    bookings = client.get("/bookings", headers=auth(session_id)).json()
    assert [b["booking_id"] for b in bookings] == ["MOCK-CASE-1", "MOCK-CASE-2", "MOCK-CASE-3", "MOCK-CASE-4"]
    first = bookings[0]
    assert first["origin"] == "JFK" and first["destination"] == "LAX"
    assert first["status"] == "canceled" and first["data_source"] == "mock" and first["rebooked"] is False
    assert first["airline"] == "Mock Air 100"
    assert bookings[2]["passenger_count"] == 3
    assert "passengers" not in first  # the list carries no passenger details


def test_booking_detail(client):
    session_id = new_session(client)
    detail = client.get("/bookings/MOCK-CASE-2", headers=auth(session_id)).json()
    assert detail["summary"]["disruption_type"] == "missed flight"
    assert detail["trip"]["data_source"] == "mock"
    assert detail["confirmation"] is None


@pytest.mark.parametrize("booking_id", ["MOCK-CASE-9", "ord_0000A1", "MOCK-CASE-1"])
def test_bookings_outside_the_session_look_unknown(client, booking_id):
    session_id = new_session(client, ["case_2"])
    response = client.get(f"/bookings/{booking_id}", headers=auth(session_id))
    assert response.status_code == 404
    assert response.json() == {"detail": "Booking not found."}


def test_sessions_are_isolated(client):
    first, second = new_session(client), new_session(client)
    session = client.app.state.sessions.get(first)
    session.toolset.tools["prepare_rebooking"](booking_id="MOCK-CASE-1", option_id="opt-1a")
    session.toolset.complete_rebooking("MOCK-CASE-1", "opt-1a")

    mine = client.get("/bookings/MOCK-CASE-1", headers=auth(first)).json()
    theirs = client.get("/bookings/MOCK-CASE-1", headers=auth(second)).json()
    assert mine["summary"]["status"] == "rebooked" and mine["confirmation"]["simulated"] is True
    assert theirs["summary"]["status"] == "canceled" and theirs["confirmation"] is None


def test_logs_hold_no_session_ids_booking_ids_or_bodies(client, caplog):
    caplog.set_level(logging.INFO, logger="travel_buddy.api")
    session_id = new_session(client, ["case_3"])
    response = client.get("/bookings/MOCK-CASE-3", headers=auth(session_id))
    assert response.headers["X-Request-Id"]
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "route=/bookings/{booking_id}" in text and "status=200" in text
    for secret in (session_id, "MOCK-CASE-3", "case_3", "Passenger"):
        assert secret not in text


def test_unexpected_errors_return_a_generic_500_and_log_only_the_type(caplog):
    app = create_app()

    @app.get("/boom")
    def boom():
        raise ValueError("Passenger Alice Example, born 1990-01-01")

    caplog.set_level(logging.INFO, logger="travel_buddy.api")
    response = TestClient(app).get("/boom")
    assert response.status_code == 500
    assert response.json() == {"detail": "Something went wrong. Please try again."}
    text = "\n".join(record.getMessage() for record in caplog.records)
    assert "error=ValueError" in text and "Alice" not in text and "1990" not in text


def test_uvicorn_access_log_is_silenced(client):
    assert logging.getLogger("uvicorn.access").disabled is True


def test_cors_allows_only_the_vite_dev_server(client):
    preflight = {"Access-Control-Request-Method": "GET", "Access-Control-Request-Headers": "X-Session-Id"}
    allowed = client.options("/bookings", headers={"Origin": "http://localhost:5173", **preflight})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "http://localhost:5173"
    blocked = client.options("/bookings", headers={"Origin": "https://evil.example", **preflight})
    assert "access-control-allow-origin" not in blocked.headers


def test_idle_sessions_expire():
    store = SessionStore(idle_seconds=-1)
    session = store.create()
    assert store.get(session.session_id) is None


def test_the_store_drops_the_oldest_session_when_full():
    store = SessionStore(max_sessions=2)
    first, second, third = store.create(), store.create(), store.create()
    assert len(store) == 2
    assert store.get(first.session_id) is None
    assert store.get(second.session_id) and store.get(third.session_id)
