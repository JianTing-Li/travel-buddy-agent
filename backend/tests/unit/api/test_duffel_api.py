"""Unit tests for Duffel test bookings in the API and tools, with a fake Duffel client (no network). Owner: Jian."""
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.app.api.main import create_app
from backend.app.services.duffel.client import DuffelTransportError
from backend.tests.unit.services.duffel.test_service import ORDER, FakeClient, offer, order, segment, slice_


class ApiFake(FakeClient):
    """FakeClient plus search, test-order creation and Duffel's change-simulating list call."""

    def __init__(self, simulates_changes: bool = True) -> None:
        super().__init__()
        self.simulates_changes = simulates_changes
        self.offers["oco_1"] = offer("oco_1")

    def search_offers(self, origin, destination, day, passengers=1, **kwargs):
        self.calls.append(("search_offers", origin, destination, day, passengers))
        return self.wrap({
            "passengers": [{"id": f"pas_{i}"} for i in range(1, passengers + 1)],
            "offers": [
                {"id": "off_ba", "owner": {"iata_code": "BA"}, "total_amount": "90.00", "total_currency": "USD"},
                {"id": "off_zz2", "owner": {"iata_code": "ZZ"}, "total_amount": "150.00", "total_currency": "USD"},
                {"id": "off_zz", "owner": {"iata_code": "ZZ"}, "total_amount": "139.04", "total_currency": "USD"},
            ],
        })

    def create_test_order(self, offer_id, amount, currency, passengers):
        self.calls.append(("create_order", offer_id, amount, currency, [p["id"] for p in passengers]))
        return self.wrap({"id": ORDER})

    def list_airline_initiated_changes(self, order_id=None):
        self.calls.append(("list_changes", order_id))
        changes = self.order["airline_initiated_changes"]
        if self.simulates_changes:
            n = len(changes) + 1
            changes.append({
                "id": f"aic_{n}", "action_taken": None, "created_at": "2026-10-15T11:00:00Z",
                "removed": [slice_([segment(f"2026-11-14T{9 + n}:03:00", f"2026-11-14T{9 + n}:41:00")])],
                "added": [slice_([segment(f"2026-11-14T{10 + n}:03:00", f"2026-11-14T{10 + n}:41:00")])],
            })
        return self.wrap(changes)


def start(fake: ApiFake | None = None, dev: bool = True) -> tuple[TestClient, str, ApiFake]:
    fake = fake or ApiFake()
    client = TestClient(create_app(dev=dev, duffel_client=fake))
    return client, client.post("/sessions").json()["session_id"], fake


def auth(session_id: str) -> dict[str, str]:
    return {"X-Session-Id": session_id}


def create_duffel(client, session_id, **body):
    return client.post("/dev/duffel-bookings", json=body or None, headers=auth(session_id))


def test_without_a_duffel_test_token_the_endpoint_says_so(monkeypatch):
    monkeypatch.setattr("backend.app.api.main.config.DUFFEL_ACCESS_TOKEN", None)
    client = TestClient(create_app(dev=True))
    session_id = client.post("/sessions").json()["session_id"]
    response = create_duffel(client, session_id)
    assert response.status_code == 503 and response.json() == {"detail": "Duffel isn't configured on the server."}


def test_a_live_token_is_never_used(monkeypatch):
    monkeypatch.setattr("backend.app.api.main.config.DUFFEL_ACCESS_TOKEN", "duffel_live_xxx")
    client = TestClient(create_app(dev=True))
    session_id = client.post("/sessions").json()["session_id"]
    assert create_duffel(client, session_id).status_code == 503


def test_creating_a_duffel_booking_books_the_cheapest_test_airline_offer():
    client, session_id, fake = start()
    response = create_duffel(client, session_id, route="lhr_ltn", passengers=2)
    assert response.status_code == 201
    body = response.json()
    assert body["booking_id"] == ORDER and body["data_source"] == "duffel" and body["status"] == "on time"
    assert body["origin"] == "LHR" and body["destination"] == "LTN" and body["rebooked"] is False
    assert body["airline"] == "Duffel Airways"
    search = [c for c in fake.calls if c[0] == "search_offers"][0]
    assert search[1:3] == ("LHR", "LTN") and search[4] == 2
    created = [c for c in fake.calls if c[0] == "create_order"][0]
    assert created[1:4] == ("off_zz", "139.04", "USD") and created[4] == ["pas_1", "pas_2"]  # ZZ only, cheapest of them


@pytest.mark.parametrize("body", [{"route": "mars"}, {"passengers": 0}, {"passengers": 4}, {"unexpected": 1}])
def test_bad_duffel_booking_requests_are_rejected(body):
    client, session_id, fake = start()
    assert create_duffel(client, session_id, **body).status_code == 422
    assert not [c for c in fake.calls if c[0] == "create_order"]


def test_dev_duffel_route_needs_dev_mode_and_a_session():
    client, session_id, _ = start(dev=False)
    assert create_duffel(client, session_id).status_code == 404
    client, _, _ = start()
    assert client.post("/dev/duffel-bookings").status_code == 401


def test_mock_and_duffel_bookings_live_side_by_side_in_one_session():
    client, session_id, _ = start()
    create_duffel(client, session_id)
    bookings = client.get("/bookings", headers=auth(session_id)).json()
    assert [b["booking_id"] for b in bookings] == ["MOCK-CASE-1", "MOCK-CASE-2", "MOCK-CASE-3", "MOCK-CASE-4", ORDER]
    assert {b["data_source"] for b in bookings} == {"mock", "duffel"}
    detail = client.get(f"/bookings/{ORDER}", headers=auth(session_id)).json()
    assert detail["trip"]["data_source"] == "duffel" and detail["confirmation"] is None
    assert detail["trip"]["passengers"] == [{"passenger_id": "pas_1", "type": "adult"}]
    assert "TravelerA" not in str(detail)
    assert client.get("/bookings/MOCK-CASE-1", headers=auth(session_id)).json()["trip"]["data_source"] == "mock"


def test_another_sessions_duffel_booking_is_unreachable():
    client, session_id, _ = start()
    other = client.post("/sessions").json()["session_id"]
    create_duffel(client, session_id)
    assert client.get(f"/bookings/{ORDER}", headers=auth(other)).status_code == 404
    assert client.post(f"/bookings/{ORDER}/changes/check", headers=auth(other)).status_code == 404
    tools = client.app.state.sessions.get(other).tools
    with pytest.raises(Exception, match="not available in this session"):
        tools["get_trip_context"](booking_id=ORDER)


def test_the_agents_tools_reach_the_duffel_booking_and_keep_sources_apart():
    client, session_id, _ = start()
    create_duffel(client, session_id)
    tools = client.app.state.sessions.get(session_id).tools
    assert tools["get_trip_context"](booking_id=ORDER)["data_source"] == "duffel"
    found = tools["search_replacements"](booking_id=ORDER)
    assert {o["data_source"] for o in found["options"]} == {"duffel"}
    with pytest.raises(Exception, match="not found"):
        tools["prepare_rebooking"](booking_id=ORDER, option_id="opt-1a")  # a mock option id never reaches Duffel
    assert tools["get_trip_context"](booking_id="MOCK-CASE-1")["data_source"] == "mock"


def test_a_duffel_rebooking_confirms_once_through_the_gate_and_the_api():
    client, session_id, fake = start()
    create_duffel(client, session_id)
    tools = client.app.state.sessions.get(session_id).tools
    option_id = tools["search_replacements"](booking_id=ORDER)["options"][0]["option_id"]
    assert tools["prepare_rebooking"](booking_id=ORDER, option_id=option_id)["validation_result"] == "valid"
    first = client.post("/confirm", json={"booking_id": ORDER, "option_id": option_id}, headers=auth(session_id))
    again = client.post("/confirm", json={"booking_id": ORDER, "option_id": option_id}, headers=auth(session_id))
    assert first.status_code == 200 and first.json()["status"] == "confirmed"
    assert first.json()["confirmation"]["data_source"] == "duffel" and "TEST API" in first.json()["confirmation"]["note"]
    assert again.json()["repeat"] is True
    assert len([c for c in fake.calls if c[0] == "confirm"]) == 1
    summary = client.get(f"/bookings/{ORDER}", headers=auth(session_id)).json()["summary"]
    assert summary["status"] == "rebooked" and summary["rebooked"] is True


def test_the_change_check_finds_a_duffel_airline_change_once():
    client, session_id, fake = start()
    create_duffel(client, session_id, route="lhr_ltn")
    fake.list_airline_initiated_changes(ORDER)  # Duffel simulates one on the order
    first = client.post(f"/bookings/{ORDER}/changes/check", headers=auth(session_id)).json()
    assert [c["change_id"] for c in first["new_changes"]] == ["aic_1"]
    assert first["new_changes"][0]["data_source"] == "duffel" and first["booking"]["status"] == "delayed"
    assert client.post(f"/bookings/{ORDER}/changes/check", headers=auth(session_id)).json()["new_changes"] == []


def test_polling_never_calls_the_change_creating_list_endpoint():
    client, session_id, fake = start()
    create_duffel(client, session_id, route="lhr_ltn")
    before = len([c for c in fake.calls if c[0] == "list_changes"])
    for _ in range(3):
        client.post(f"/bookings/{ORDER}/changes/check", headers=auth(session_id))
    assert len([c for c in fake.calls if c[0] == "list_changes"]) == before == 0


def test_the_dev_disrupt_button_creates_a_duffel_change_that_polling_finds():
    client, session_id, _ = start()
    create_duffel(client, session_id, route="lhr_ltn")
    made = client.post(f"/dev/bookings/{ORDER}/disrupt", json={"kind": "delay", "delay_minutes": 30}, headers=auth(session_id))
    assert made.status_code == 201 and made.json()["data_source"] == "duffel" and made.json()["kind"] == "delay"
    found = client.post(f"/bookings/{ORDER}/changes/check", headers=auth(session_id)).json()
    assert [c["change_id"] for c in found["new_changes"]] == [made.json()["change_id"]]


def test_duffel_cannot_simulate_cancellations_or_changes_off_the_lhr_ltn_route():
    client, session_id, _ = start()
    create_duffel(client, session_id)
    cancel = client.post(f"/dev/bookings/{ORDER}/disrupt", json={"kind": "cancellation"}, headers=auth(session_id))
    assert cancel.status_code == 422 and "only simulates delays" in cancel.json()["detail"]
    quiet_client, quiet_session, _ = start(ApiFake(simulates_changes=False))
    create_duffel(quiet_client, quiet_session)
    none = quiet_client.post(f"/dev/bookings/{ORDER}/disrupt", json={"kind": "delay", "delay_minutes": 30},
                             headers=auth(quiet_session))
    assert none.status_code == 409 and "LHR to LTN" in none.json()["detail"]


def test_mock_faults_cannot_target_a_duffel_booking():
    client, session_id, _ = start()
    create_duffel(client, session_id)
    response = client.post(f"/dev/bookings/{ORDER}/faults", json={"faults": ["tool_failure"]}, headers=auth(session_id))
    assert response.status_code == 409 and "mock bookings only" in response.json()["detail"]


def test_an_unreachable_duffel_gives_a_safe_502():
    client, session_id, fake = start()
    create_duffel(client, session_id)

    def drop(order_id):
        raise DuffelTransportError(httpx.ConnectError("secret-host"), may_have_reached_duffel=False)

    fake.get_order = drop
    response = client.get(f"/bookings/{ORDER}", headers=auth(session_id))
    assert response.status_code == 502
    assert response.json() == {"detail": "Duffel could not be reached. Try again shortly."}


def test_the_session_booking_limit_counts_duffel_bookings_too():
    from backend.app.api.sessions import MAX_BOOKINGS_PER_SESSION
    client, session_id, _ = start()
    session = client.app.state.sessions.get(session_id)
    for seed in range(MAX_BOOKINGS_PER_SESSION - len(session.booking_ids)):
        assert client.post("/dev/bookings", json={"seed": seed}, headers=auth(session_id)).status_code == 201
    over = create_duffel(client, session_id)
    assert over.status_code == 409 and "at most" in over.json()["detail"]
