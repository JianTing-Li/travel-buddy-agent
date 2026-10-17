"""Unit tests for the /dev test endpoints: only in dev mode, mock-only, scoped to the session. Owner: Jian."""
from types import SimpleNamespace as NS

import pytest
from fastapi.testclient import TestClient

from backend.app.api.main import create_app
from backend.app.api.sessions import MAX_BOOKINGS_PER_SESSION


def start(dev=True, model=None) -> tuple[TestClient, str]:
    client = TestClient(create_app(dev=dev, model_client=model, model="fake-model" if model else None))
    return client, client.post("/sessions").json()["session_id"]


def auth(session_id: str) -> dict[str, str]:
    return {"X-Session-Id": session_id}


def create(client, session_id, **body):
    return client.post("/dev/bookings", json=body or None, headers=auth(session_id))


def test_dev_routes_do_not_exist_without_dev_mode():
    client, session_id = start(dev=False)
    assert create(client, session_id).status_code == 404
    assert client.post("/dev/bookings/MOCK-CASE-1/disrupt", json={"kind": "cancellation"}, headers=auth(session_id)).status_code == 404
    assert client.post("/dev/bookings/MOCK-CASE-1/faults", json={"faults": []}, headers=auth(session_id)).status_code == 404
    assert "/dev/bookings" not in client.get("/openapi.json").json()["paths"]


def test_dev_routes_still_need_a_session():
    client, _ = start()
    assert client.post("/dev/bookings").status_code == 401


def test_create_a_random_booking_with_a_seed_that_reproduces_it():
    client, session_id = start()
    first = create(client, session_id, seed=11)
    assert first.status_code == 201
    body = first.json()
    assert body["seed"] == 11 and body["scenario"] is None and body["booking"]["booking_id"] == "MOCK-GEN-11"
    assert body["booking"]["data_source"] == "mock"
    other_client, other_session = start()
    again = create(other_client, other_session, seed=11).json()
    assert again["booking"] == body["booking"]  # same seed, same booking


def test_create_without_a_body_picks_a_seed_and_reports_it():
    client, session_id = start()
    body = create(client, session_id).json()
    assert 0 <= body["seed"] <= 999_999 and body["booking"]["booking_id"] == f"MOCK-GEN-{body['seed']}"


def test_create_an_eval_case_copy():
    client, session_id = start()
    body = create(client, session_id, scenario="case_3", seed=4).json()
    assert body["booking"]["booking_id"] == "MOCK-CASE-3-G4" and body["booking"]["passenger_count"] == 3
    assert body["scenario"] == "case_3"


def test_a_new_booking_appears_in_the_list_and_detail_for_this_session_only():
    client, session_id = start()
    other = client.post("/sessions").json()["session_id"]
    create(client, session_id, seed=21)
    ids = [b["booking_id"] for b in client.get("/bookings", headers=auth(session_id)).json()]
    assert ids[-1] == "MOCK-GEN-21"
    assert client.get("/bookings/MOCK-GEN-21", headers=auth(session_id)).status_code == 200
    assert client.get("/bookings/MOCK-GEN-21", headers=auth(other)).status_code == 404


@pytest.mark.parametrize("body", [{"seed": -1}, {"seed": 1_000_000}, {"scenario": "case_99"}, {"unexpected": 1}])
def test_bad_create_requests_are_rejected(body):
    client, session_id = start()
    assert create(client, session_id, **body).status_code == 422


def test_creating_the_same_seed_twice_is_a_conflict():
    client, session_id = start()
    assert create(client, session_id, seed=5).status_code == 201
    assert create(client, session_id, seed=5).status_code == 409


def test_a_session_has_a_booking_limit():
    client, session_id = start()
    existing = len(client.get("/bookings", headers=auth(session_id)).json())
    for seed in range(MAX_BOOKINGS_PER_SESSION - existing):
        assert create(client, session_id, seed=seed).status_code == 201
    over = create(client, session_id, seed=999)
    assert over.status_code == 409 and "at most" in over.json()["detail"]


def test_the_tools_can_reach_a_generated_booking_but_not_other_sessions_bookings():
    client, session_id = start()
    create(client, session_id, seed=33)
    session = client.app.state.sessions.get(session_id)
    assert session.tools["get_trip_context"](booking_id="MOCK-GEN-33")["data_source"] == "mock"
    other = client.post("/sessions").json()["session_id"]
    other_session = client.app.state.sessions.get(other)
    with pytest.raises(Exception, match="not available in this session"):
        other_session.tools["get_trip_context"](booking_id="MOCK-GEN-33")


def test_disrupt_creates_a_change_that_the_normal_check_finds_once():
    client, session_id = start()
    made = client.post("/dev/bookings/MOCK-CASE-3/disrupt", json={"kind": "delay", "delay_minutes": 120},
                       headers=auth(session_id))
    assert made.status_code == 201 and made.json()["kind"] == "delay" and made.json()["simulated"] is True
    found = client.post("/bookings/MOCK-CASE-3/changes/check", headers=auth(session_id)).json()
    assert [c["change_id"] for c in found["new_changes"]] == [made.json()["change_id"]]
    assert found["booking"]["status"] == "delayed"
    assert client.post("/bookings/MOCK-CASE-3/changes/check", headers=auth(session_id)).json()["new_changes"] == []


def test_disrupt_with_a_cancellation_and_on_a_generated_booking():
    client, session_id = start()
    create(client, session_id, seed=2)
    made = client.post("/dev/bookings/MOCK-GEN-2/disrupt", json={"kind": "cancellation"}, headers=auth(session_id))
    assert made.status_code == 201 and made.json()["kind"] == "cancellation"
    assert client.get("/bookings/MOCK-GEN-2", headers=auth(session_id)).json()["summary"]["status"] == "canceled"


@pytest.mark.parametrize("body", [{"kind": "delay"}, {"kind": "delay", "delay_minutes": 0},
                                  {"kind": "delay", "delay_minutes": 5000}, {"kind": "strike"}, {}])
def test_bad_disruptions_are_rejected(body):
    client, session_id = start()
    assert client.post("/dev/bookings/MOCK-CASE-1/disrupt", json=body, headers=auth(session_id)).status_code == 422


def test_disrupting_a_rebooked_booking_is_a_conflict():
    client, session_id = start()
    session = client.app.state.sessions.get(session_id)
    session.service.prepare_rebooking("MOCK-CASE-1", "opt-1a")
    session.service.complete_rebooking("MOCK-CASE-1", "opt-1a")
    done = client.post("/dev/bookings/MOCK-CASE-1/disrupt", json={"kind": "cancellation"}, headers=auth(session_id))
    assert done.status_code == 409 and "already rebooked" in done.json()["detail"]


def test_disrupt_and_faults_respect_booking_ownership():
    client, session_id = start()
    only_case_2 = client.post("/sessions", json={"scenarios": ["case_2"]}).json()["session_id"]
    assert client.post("/dev/bookings/MOCK-CASE-1/disrupt", json={"kind": "cancellation"},
                       headers=auth(only_case_2)).status_code == 404
    assert client.post("/dev/bookings/MOCK-CASE-1/faults", json={"faults": []}, headers=auth(only_case_2)).status_code == 404
    assert client.post("/dev/bookings/ord_0000A1/faults", json={"faults": []}, headers=auth(session_id)).status_code == 404


def test_faults_can_be_set_and_cleared_and_unknown_ones_are_rejected():
    client, session_id = start()
    path = "/dev/bookings/MOCK-CASE-1/faults"
    assert client.post(path, json={"faults": ["wrong_currency", "tool_failure"]}, headers=auth(session_id)).json() == {
        "faults": ["tool_failure", "wrong_currency"]}
    assert client.post(path, json={"faults": []}, headers=auth(session_id)).json() == {"faults": []}
    bad = client.post(path, json={"faults": ["nope"]}, headers=auth(session_id))
    assert bad.status_code == 422 and "Unknown faults" in bad.json()["detail"]


def test_a_tool_failure_fault_reaches_the_agent_as_a_tool_error_and_clears():
    def script(*blocks):
        return NS(content=list(blocks), stop_reason="end_turn")

    # complete limits: a search without them is refused by Cheich's required-limits check before it reaches the fault
    limits = {"budget_additional_cost": 0, "currency": "USD", "arrive_by": "2026-10-15T15:00-07:00",
              "max_connections": 1, "passenger_count": 1}
    tool = NS(type="tool_use", id="t1", name="search_replacements", input={"booking_id": "MOCK-CASE-1", "limits": limits})
    requests: list[list] = []

    class Model:
        replies = [script(tool), script(NS(type="text", text="The search failed; I will hand this off."))]
        messages = NS(create=lambda **kw: (requests.append([dict(m) for m in kw["messages"]]), Model.replies.pop(0))[1])

    client, session_id = start(model=Model)
    client.post("/dev/bookings/MOCK-CASE-1/faults", json={"faults": ["tool_failure"]}, headers=auth(session_id))
    reply = client.post("/chat", json={"booking_id": "MOCK-CASE-1", "message": "search"}, headers=auth(session_id))
    assert reply.status_code == 200 and reply.json()["stopped_reason"] == "reply"
    result = requests[1][-1]["content"][0]
    assert result["is_error"] and "Simulated tool failure" in result["content"]


def test_dev_endpoint_logs_hold_no_booking_ids_or_seeds(caplog):
    import logging
    client, session_id = start()
    caplog.set_level(logging.INFO, logger="travel_buddy.api")
    create(client, session_id, seed=424242)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "route=/dev/bookings" in text and "424242" not in text and session_id not in text


# --- reset ---------------------------------------------------------------------------------

def reset(client, session_id):
    return client.post("/dev/reset", headers=auth(session_id))


def test_reset_is_dev_only_and_needs_a_session():
    client, session_id = start(dev=False)
    assert reset(client, session_id).status_code == 404
    client, _ = start()
    assert client.post("/dev/reset").status_code == 401


def test_reset_puts_the_session_back_to_its_first_bookings():
    client, session_id = start()
    session = client.app.state.sessions.get(session_id)
    create(client, session_id, seed=8)
    client.post("/dev/bookings/MOCK-CASE-3/disrupt", json={"kind": "delay", "delay_minutes": 30}, headers=auth(session_id))
    client.post("/dev/bookings/MOCK-CASE-2/faults", json={"faults": ["tool_failure"]}, headers=auth(session_id))
    session.tools["prepare_rebooking"](booking_id="MOCK-CASE-1", option_id="opt-1a")
    client.post("/confirm", json={"booking_id": "MOCK-CASE-1", "option_id": "opt-1a"}, headers=auth(session_id))
    session.histories["MOCK-CASE-1"] = [{"role": "user", "content": "hi"}]

    response = reset(client, session_id)
    assert response.status_code == 200
    assert response.json() == {"booking_ids": ["MOCK-CASE-1", "MOCK-CASE-2", "MOCK-CASE-3", "MOCK-CASE-4"]}
    bookings = {b["booking_id"]: b for b in client.get("/bookings", headers=auth(session_id)).json()}
    assert "MOCK-GEN-8" not in bookings  # generated booking gone
    assert bookings["MOCK-CASE-1"]["rebooked"] is False and bookings["MOCK-CASE-1"]["status"] == "canceled"
    assert bookings["MOCK-CASE-3"]["status"] == "canceled"  # the simulated delay is gone
    assert client.post("/bookings/MOCK-CASE-3/changes/check", headers=auth(session_id)).json()["new_changes"] == []
    session = client.app.state.sessions.get(session_id)
    assert session.histories == {} and session.prepared == {} and not any(session.notices.values())
    assert session.service.get_faults("MOCK-CASE-2") == []
    assert session.tools["search_replacements"](booking_id="MOCK-CASE-2")["options"]  # no tool_failure any more


def test_after_a_reset_the_same_seed_can_be_generated_again_and_rebooking_works():
    client, session_id = start()
    assert create(client, session_id, seed=9).status_code == 201
    reset(client, session_id)
    assert create(client, session_id, seed=9).status_code == 201  # no "already exists"
    session = client.app.state.sessions.get(session_id)
    session.tools["prepare_rebooking"](booking_id="MOCK-CASE-1", option_id="opt-1a")
    assert client.post("/confirm", json={"booking_id": "MOCK-CASE-1", "option_id": "opt-1a"},
                       headers=auth(session_id)).json()["status"] == "confirmed"


def test_reset_keeps_the_session_id_and_leaves_other_sessions_alone():
    client, mine = start()
    other = client.post("/sessions").json()["session_id"]
    create(client, other, seed=12)
    reset(client, mine)
    assert client.get("/bookings", headers=auth(mine)).status_code == 200  # same id still works
    assert "MOCK-GEN-12" in [b["booking_id"] for b in client.get("/bookings", headers=auth(other)).json()]


def test_a_session_limited_to_some_scenarios_keeps_them_after_reset():
    client = TestClient(create_app(dev=True))
    session_id = client.post("/sessions", json={"scenarios": ["case_2"]}).json()["session_id"]
    create(client, session_id, seed=3)
    assert reset(client, session_id).json() == {"booking_ids": ["MOCK-CASE-2"]}
