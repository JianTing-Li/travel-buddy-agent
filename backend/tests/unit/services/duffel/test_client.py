"""Unit tests for the Duffel client using a mocked HTTP transport (no network). Owner: Jian."""
import json

import httpx
import pytest

from backend.app.services.duffel.client import (
    DuffelApiError,
    DuffelClient,
    DuffelConfigError,
    DuffelTransportError,
)

TOKEN = "duffel_test_unit_test_token"


def make_client(handler) -> tuple[DuffelClient, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def recording(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.Client(base_url="https://api.duffel.com", transport=httpx.MockTransport(recording))
    return DuffelClient(TOKEN, http=http), seen


def ok(data) -> httpx.Response:
    return httpx.Response(200, json={"data": data})


def body_of(request: httpx.Request) -> dict:
    return json.loads(request.content)


def test_rejects_missing_token(monkeypatch):
    monkeypatch.setattr("backend.app.services.duffel.client.config.DUFFEL_ACCESS_TOKEN", None)
    with pytest.raises(DuffelConfigError):
        DuffelClient()


def test_rejects_live_token_without_echoing_it():
    with pytest.raises(DuffelConfigError) as exc:
        DuffelClient("duffel_live_secret_value")
    assert "secret_value" not in str(exc.value)


def test_results_are_tagged_duffel_and_data_is_unchanged():
    client, _ = make_client(lambda r: ok({"id": "ord_1", "total_amount": "10.00"}))
    result = client.get_order("ord_1")
    assert result == {"data_source": "duffel", "data": {"id": "ord_1", "total_amount": "10.00"}}


def test_sends_auth_and_version_headers():
    client, seen = make_client(lambda r: ok({}))
    client.get_order("ord_1")
    request = seen[0]
    assert request.method == "GET" and request.url.path == "/air/orders/ord_1"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert request.headers["Duffel-Version"] == "v2"


def test_search_offers_request_shape():
    client, seen = make_client(lambda r: ok({"offers": []}))
    client.search_offers("JFK", "LAX", "2026-11-13", passengers=3, max_connections=0)
    request = seen[0]
    assert request.url.path == "/air/offer_requests"
    assert request.url.params["return_offers"] == "true"
    assert body_of(request) == {
        "data": {
            "slices": [{"origin": "JFK", "destination": "LAX", "departure_date": "2026-11-13"}],
            "passengers": [{"type": "adult"}] * 3,
            "cabin_class": "economy",
            "max_connections": 0,
        }
    }


def test_create_test_order_pays_with_the_offer_total():
    client, seen = make_client(lambda r: ok({"id": "ord_1"}))
    client.create_test_order("off_1", "139.04", "USD", [{"id": "pas_1"}])
    assert body_of(seen[0])["data"] == {
        "selected_offers": ["off_1"],
        "payments": [{"type": "balance", "currency": "USD", "amount": "139.04"}],
        "passengers": [{"id": "pas_1"}],
    }


def test_list_airline_changes_filters_by_order_only_when_given():
    client, seen = make_client(lambda r: ok([]))
    client.list_airline_initiated_changes()
    client.list_airline_initiated_changes("ord_1")
    assert "order_id" not in seen[0].url.params
    assert seen[1].url.params["order_id"] == "ord_1"


def test_accept_airline_change_posts_without_a_body():
    client, seen = make_client(lambda r: ok({"id": "aic_1", "action_taken": "accepted"}))
    result = client.accept_airline_initiated_change("aic_1")
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/air/airline_initiated_changes/aic_1/actions/accept"
    assert seen[0].content == b""
    assert result["data"]["action_taken"] == "accepted"


def test_accepting_a_stale_airline_change_is_an_api_error_with_its_code():
    error = {"type": "invalid_state_error", "code": "stale_airline_initiated_change_accept",
             "title": "Not the latest", "message": "The airline-initiated change is not the latest for this order."}
    client, _ = make_client(lambda r: httpx.Response(422, json={"errors": [error]}))
    with pytest.raises(DuffelApiError) as exc:
        client.accept_airline_initiated_change("aic_old")
    assert exc.value.codes == ["stale_airline_initiated_change_accept"]


def test_create_order_change_request_body():
    client, seen = make_client(lambda r: ok({"order_change_offers": []}))
    client.create_order_change_request("ord_1", "sli_1", "JFK", "LAX", "2026-11-14")
    assert body_of(seen[0])["data"] == {
        "order_id": "ord_1",
        "slices": {
            "remove": [{"slice_id": "sli_1"}],
            "add": [{"origin": "JFK", "destination": "LAX", "departure_date": "2026-11-14", "cabin_class": "economy"}],
        },
    }


def test_list_and_get_order_change_offers():
    client, seen = make_client(lambda r: ok([]))
    client.list_order_change_offers("ocr_1")
    client.get_order_change_offer("oco_1")
    assert seen[0].url.params["order_change_request_id"] == "ocr_1"
    assert seen[0].url.params["sort"] == "change_total_amount"
    assert seen[1].url.path == "/air/order_change_offers/oco_1"


def test_create_pending_change_sends_selected_offer():
    client, seen = make_client(lambda r: ok({"id": "ocg_1"}))
    client.create_pending_order_change("oco_1")
    assert seen[0].url.path == "/air/order_changes"
    assert body_of(seen[0]) == {"data": {"selected_order_change_offer": "oco_1"}}


def test_confirm_sends_payment_with_the_given_amount_unchanged():
    client, seen = make_client(lambda r: ok({"confirmed_at": "2026-10-14T00:00:00Z"}))
    client.confirm_order_change("ocg_1", "125.00", "USD")
    assert seen[0].url.path == "/air/order_changes/ocg_1/actions/confirm"
    assert body_of(seen[0])["data"] == {"payment": {"type": "balance", "currency": "USD", "amount": "125.00"}}


def test_api_error_carries_status_type_and_code():
    error = {"type": "invalid_state_error", "code": "order_change_already_confirmed",
             "title": "Order change already confirmed", "message": "The order change has already been confirmed."}
    client, _ = make_client(lambda r: httpx.Response(422, json={"errors": [error]}))
    with pytest.raises(DuffelApiError) as exc:
        client.confirm_order_change("ocg_1", "125.00", "USD")
    assert exc.value.status == 422
    assert exc.value.codes == ["order_change_already_confirmed"]
    assert TOKEN not in str(exc.value)


def test_error_message_is_truncated():
    long_message = "x" * 1000
    client, _ = make_client(lambda r: httpx.Response(400, json={"errors": [{"message": long_message}]}))
    with pytest.raises(DuffelApiError) as exc:
        client.get_order("ord_1")
    assert len(exc.value.errors[0]["message"]) == 200


@pytest.mark.parametrize("response", [
    httpx.Response(200, json={"unexpected": True}),
    httpx.Response(502, text="<html>bad gateway</html>"),
])
def test_unexpected_body_or_non_json_is_an_api_error(response):
    client, _ = make_client(lambda r: response)
    with pytest.raises(DuffelApiError) as exc:
        client.get_order("ord_1")
    assert exc.value.status == response.status_code


def test_server_error_on_confirm_is_not_retried():
    client, seen = make_client(lambda r: httpx.Response(500, json={"errors": []}))
    with pytest.raises(DuffelApiError):
        client.confirm_order_change("ocg_1", "125.00", "USD")
    assert len(seen) == 1


def test_timeout_on_confirm_is_flagged_as_possibly_sent():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    client, seen = make_client(handler)
    with pytest.raises(DuffelTransportError) as exc:
        client.confirm_order_change("ocg_1", "125.00", "USD")
    assert exc.value.may_have_reached_duffel is True
    assert len(seen) == 1


def test_connect_failure_is_flagged_as_not_sent():
    def handler(request):
        raise httpx.ConnectError("no route", request=request)

    client, _ = make_client(handler)
    with pytest.raises(DuffelTransportError) as exc:
        client.get_order("ord_1")
    assert exc.value.may_have_reached_duffel is False
