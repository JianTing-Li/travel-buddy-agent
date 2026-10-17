"""Unit tests for DuffelService: mapping Duffel test data to the contract and the safety rules. Owner: Jian.

A fake client returns data in the shapes recorded in docs/duffel-notes.md; nothing touches the network.
"""
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest

from backend.app.contract.models import Limits, Option, TripContext
from backend.app.services.duffel.client import DuffelApiError, DuffelTransportError
from backend.app.services.duffel.service import DuffelService, DuffelServiceError
from backend.app.services.errors import (
    AlreadyRebookedError,
    RebookingNotAllowedError,
    ServiceError,
    UnknownBookingError,
    UnknownOptionError,
)

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)
ORDER = "ord_test1"


def segment(dep: str, arr: str, origin="LHR", dest="LTN", zone_o="Europe/London", zone_d="Europe/London"):
    return {
        "departing_at": dep, "arriving_at": arr,
        "origin": {"iata_code": origin, "time_zone": zone_o}, "destination": {"iata_code": dest, "time_zone": zone_d},
        "marketing_carrier": {"name": "Duffel Airways", "iata_code": "ZZ"}, "marketing_carrier_flight_number": "123",
    }


def slice_(segments, origin="LHR", dest="LTN", duration="PT38M", id_="sli_1"):
    return {"id": id_, "origin": {"iata_code": origin}, "destination": {"iata_code": dest}, "duration": duration,
            "segments": segments}


def order(actions=("cancel", "change", "update"), changes=(), live=False, **extra):
    return {
        "id": ORDER, "live_mode": live, "available_actions": list(actions), "booking_reference": "ABC123",
        "slices": [slice_([segment("2026-11-14T10:03:00", "2026-11-14T10:41:00")])],
        "passengers": [{"id": "pas_1", "type": "adult", "given_name": "Test", "family_name": "TravelerA"}],
        "airline_initiated_changes": list(changes), **extra,
    }


def offer(id_, amount="125.00", currency="USD", dep="2026-11-14T12:00:00", arr="2026-11-14T12:38:00",
          allowed=True, expires="2099-01-01T00:00:00Z", segments=1, new_total="264.08"):
    segs = [segment(dep, arr)] * segments
    return {
        "id": id_, "change_total_amount": amount, "change_total_currency": currency, "new_total_amount": new_total,
        "new_total_currency": "USD", "penalty_total_amount": "25.00", "expires_at": expires,
        "conditions": {"change_before_departure": {"allowed": allowed, "penalty_amount": "25.00"}},
        "slices": {"add": [slice_(segs)], "remove": []},
    }


class FakeClient:
    """Answers like DuffelClient. Responses can be replaced per test; every call is recorded."""

    def __init__(self) -> None:
        self.order = order()
        self.requests_by_date: dict[str, list[dict]] = {"2026-11-14": [offer("oco_1"), offer("oco_2", dep="2026-11-14T18:00:00", arr="2026-11-14T18:38:00")]}
        self.offers: dict[str, dict] = {}
        self.pending: dict[str, Any] = {"id": "ocg_1", "change_total_amount": "125.00", "change_total_currency": "USD"}
        self.confirm_error: Exception | None = None
        self.calls: list[tuple] = []

    @staticmethod
    def wrap(data):
        return {"data_source": "duffel", "data": data}

    def get_order(self, order_id):
        self.calls.append(("get_order", order_id))
        if order_id != ORDER:
            raise DuffelApiError(404, [{"type": "invalid_request_error", "code": "not_found"}])
        return self.wrap(self.order)

    def create_order_change_request(self, order_id, slice_id, origin, destination, day, cabin="economy"):
        self.calls.append(("change_request", day))
        offers = self.requests_by_date.get(day, [])
        for o in offers:
            self.offers.setdefault(o["id"], o)
        return self.wrap({"id": f"ocr_{day}", "order_change_offers": offers})

    def get_order_change_offer(self, offer_id):
        self.calls.append(("get_offer", offer_id))
        return self.wrap(self.offers[offer_id])

    def create_pending_order_change(self, offer_id):
        self.calls.append(("pending", offer_id))
        return self.wrap(self.pending)

    def confirm_order_change(self, change_id, amount, currency):
        self.calls.append(("confirm", change_id, amount, currency))
        if self.confirm_error:
            raise self.confirm_error
        return self.wrap({**self.pending, "confirmed_at": "2026-10-15T12:00:01Z"})


@pytest.fixture
def client() -> FakeClient:
    return FakeClient()


@pytest.fixture
def service(client) -> DuffelService:
    svc = DuffelService(client, now=lambda: NOW)
    svc.add_booking(ORDER)
    return svc


def calls(client, name):
    return [c for c in client.calls if c[0] == name]


# --- bookings -------------------------------------------------------------------------------

def test_only_duffel_test_orders_can_be_added(client):
    svc = DuffelService(client, now=lambda: NOW)
    with pytest.raises(UnknownBookingError):
        svc.add_booking("MOCK-CASE-1")
    with pytest.raises(UnknownBookingError):
        svc.add_booking("ord_missing")
    client.order = order(live=True)
    with pytest.raises(ServiceError, match="test-mode"):
        svc.add_booking(ORDER)
    assert svc.booking_ids() == []


def test_untracked_orders_are_unknown(service):
    with pytest.raises(UnknownBookingError):
        service.get_trip_context("ord_other")


# --- trip context ---------------------------------------------------------------------------

def test_trip_context_maps_the_order_without_passenger_names(service):
    trip = service.get_trip_context(ORDER)
    assert isinstance(trip, TripContext) and trip.data_source == "duffel"
    itinerary = trip.original_itinerary
    assert itinerary.origin == "LHR" and itinerary.destination == "LTN"
    assert itinerary.departs == "2026-11-14T10:03+00:00" and itinerary.flight == "ZZ123"
    assert itinerary.status == "on time" and trip.disruption_details.type == "none reported"
    assert [p.model_dump() for p in trip.passengers] == [{"passenger_id": "pas_1", "type": "adult"}]
    assert "TravelerA" not in str(trip.model_dump())


def test_an_open_airline_change_marks_the_trip_delayed(client, service):
    client.order = order(changes=[{"id": "aic_1", "action_taken": None}])
    assert service.get_trip_context(ORDER).original_itinerary.status == "delayed"


def test_times_get_the_airports_utc_offset():
    svc = DuffelService(FakeClient(), now=lambda: NOW)
    fake = svc._client
    fake.order["slices"] = [slice_([segment("2026-11-14T08:00:00", "2026-11-14T11:15:00", "JFK", "LAX",
                                            "America/New_York", "America/Los_Angeles")], "JFK", "LAX", "PT6H15M")]
    svc.add_booking(ORDER)
    itinerary = svc.get_trip_context(ORDER).original_itinerary
    assert itinerary.departs == "2026-11-14T08:00-05:00" and itinerary.arrives == "2026-11-14T11:15-08:00"


# --- search ----------------------------------------------------------------------------------

def test_search_maps_offers_using_change_total_not_new_total(service):
    options = service.search_replacements(ORDER)
    assert [o.option_id for o in options] == ["oco_1", "oco_2"]
    first = options[0]
    assert isinstance(first, Option) and first.data_source == "duffel"
    assert first.additional_cost == 125.0 and first.currency == "USD"  # never the 264.08 new_total_amount
    assert first.eligibility == "eligible" and first.validity == "valid"
    d = first.flight_details
    assert d.departs == "2026-11-14T12:00+00:00" and d.duration == "0h 38m" and d.connections == 0
    assert d.airline == "Duffel Airways" and d.simulated is True


def test_identical_offers_are_shown_once(client, service):
    client.requests_by_date["2026-11-14"] = [offer("oco_1"), offer("oco_dup"), offer("oco_3", amount="0.00")]
    assert [o.option_id for o in service.search_replacements(ORDER)] == ["oco_1", "oco_3"]


def test_search_tries_the_next_day_when_the_original_date_has_nothing(client, service):
    client.requests_by_date = {"2026-11-15": [offer("oco_next", dep="2026-11-15T09:00:00", arr="2026-11-15T09:38:00")]}
    assert [o.option_id for o in service.search_replacements(ORDER)] == ["oco_next"]
    assert [c[1] for c in calls(client, "change_request")] == ["2026-11-14", "2026-11-15"]


def test_search_with_no_offers_returns_an_empty_list(client, service):
    client.requests_by_date = {}
    assert service.search_replacements(ORDER) == []


def test_offers_without_a_cost_or_currency_are_dropped(client, service):
    client.requests_by_date["2026-11-14"] = [offer("oco_1", amount=None), offer("oco_2", currency=""), offer("oco_3")]
    assert [o.option_id for o in service.search_replacements(ORDER)] == ["oco_3"]


def test_an_offer_that_would_refund_is_left_out(client, service):
    # Contract v1: additional_cost is never negative; refunds are out of scope for MVP 1.
    client.requests_by_date["2026-11-14"] = [offer("oco_refund", amount="-30.00"), offer("oco_ok")]
    assert [o.option_id for o in service.search_replacements(ORDER)] == ["oco_ok"]


def test_offers_without_flight_times_or_offsets_are_left_out(client, service):
    no_times = offer("oco_1")
    no_times["slices"]["add"][0]["segments"][0]["departing_at"] = None
    no_zone = offer("oco_2", dep="2026-11-14T13:00:00", arr="2026-11-14T13:38:00")
    no_zone["slices"]["add"][0]["segments"][0]["origin"]["time_zone"] = None
    client.requests_by_date["2026-11-14"] = [no_times, no_zone, offer("oco_3", dep="2026-11-14T15:00:00")]
    assert [o.option_id for o in service.search_replacements(ORDER)] == ["oco_3"]


def test_changes_not_allowed_by_the_fare_mean_unknown_eligibility(client, service):
    client.requests_by_date["2026-11-14"] = [offer("oco_1", allowed=False)]
    assert service.search_replacements(ORDER)[0].eligibility == "unknown"


def test_expired_offers_are_marked_expired(client, service):
    client.requests_by_date["2026-11-14"] = [offer("oco_1", expires="2026-10-15T11:59:00Z")]
    assert service.search_replacements(ORDER)[0].validity == "expired"


def test_an_order_duffel_will_not_change_cannot_be_searched(client, service):
    client.order = order(actions=("cancel", "update"))
    with pytest.raises(RebookingNotAllowedError, match="does not allow changes"):
        service.search_replacements(ORDER)
    assert calls(client, "change_request") == []


def test_duffel_errors_become_safe_service_errors(client, service):
    def boom(*args):
        raise DuffelApiError(422, [{"type": "invalid_state_error", "code": "order_not_changeable",
                                    "message": "secret-ish detail"}])

    client.create_order_change_request = boom
    with pytest.raises(DuffelServiceError) as exc:
        service.search_replacements(ORDER)
    assert str(exc.value) == "Duffel returned 422 (order_not_changeable)."


def test_unreachable_duffel_on_a_read_is_a_service_error(client, service):
    def drop(*args):
        raise DuffelTransportError(httpx.ConnectError("x"), may_have_reached_duffel=False)

    client.get_order = drop
    with pytest.raises(DuffelServiceError, match="could not be reached"):
        service.get_trip_context(ORDER)


# --- prepare --------------------------------------------------------------------------------

def test_only_offers_from_this_bookings_search_can_be_prepared(service):
    with pytest.raises(UnknownOptionError):
        service.prepare_rebooking(ORDER, "oco_1")  # not searched yet
    service.search_replacements(ORDER)
    with pytest.raises(UnknownOptionError):
        service.prepare_rebooking(ORDER, "oco_someone_else")


def test_prepare_rechecks_the_offer_with_duffel(client, service):
    service.search_replacements(ORDER)
    result = service.prepare_rebooking(ORDER, "oco_1")
    assert result.validation_result == "valid" and result.changes_to_review == []
    assert ("get_offer", "oco_1") in client.calls


def test_a_price_change_since_search_must_be_reviewed(client, service):
    service.search_replacements(ORDER)
    client.offers["oco_1"] = offer("oco_1", amount="135.00")
    changed = service.prepare_rebooking(ORDER, "oco_1")
    assert changed.validation_result == "changed"
    assert changed.changes_to_review == ["Extra cost changed from 125 USD to 135 USD."]
    assert service.prepare_rebooking(ORDER, "oco_1").validation_result == "valid"


def test_an_offer_that_expired_since_search_is_unavailable(client, service):
    service.search_replacements(ORDER)
    client.offers["oco_1"] = offer("oco_1", expires="2026-10-15T11:00:00Z")
    assert service.prepare_rebooking(ORDER, "oco_1").validation_result == "unavailable"


# --- complete -------------------------------------------------------------------------------

def prepared(service):
    service.search_replacements(ORDER)
    assert service.prepare_rebooking(ORDER, "oco_1").validation_result == "valid"


def test_complete_creates_a_pending_change_and_confirms_the_reviewed_cost(client, service):
    prepared(service)
    confirmation = service.complete_rebooking(ORDER, "oco_1")
    assert calls(client, "confirm") == [("confirm", "ocg_1", "125.00", "USD")]
    assert confirmation["confirmation_id"] == "ocg_1" and confirmation["data_source"] == "duffel"
    assert confirmation["additional_cost"] == 125.0 and "TEST API" in confirmation["note"]
    assert service.get_confirmation(ORDER) == confirmation
    assert service.get_trip_context(ORDER).original_itinerary.status == "rebooked"


def test_complete_requires_a_prepare_of_the_same_option(client, service):
    service.search_replacements(ORDER)
    with pytest.raises(RebookingNotAllowedError, match="not prepared"):
        service.complete_rebooking(ORDER, "oco_1")
    assert calls(client, "pending") == []


def test_complete_refuses_when_the_offer_changed_after_prepare(client, service):
    prepared(service)
    client.offers["oco_1"] = offer("oco_1", amount="150.00")
    with pytest.raises(RebookingNotAllowedError, match="changed after it was prepared"):
        service.complete_rebooking(ORDER, "oco_1")
    assert calls(client, "pending") == []


def test_complete_stops_if_the_pending_change_quotes_a_different_cost(client, service):
    prepared(service)
    client.pending = {"id": "ocg_1", "change_total_amount": "140.00", "change_total_currency": "USD"}
    with pytest.raises(RebookingNotAllowedError, match="different cost"):
        service.complete_rebooking(ORDER, "oco_1")
    assert calls(client, "confirm") == [] and service.get_confirmation(ORDER) is None


def test_a_booking_is_rebooked_only_once(service):
    prepared(service)
    service.complete_rebooking(ORDER, "oco_1")
    with pytest.raises(AlreadyRebookedError):
        service.complete_rebooking(ORDER, "oco_1")
    assert service.prepare_rebooking(ORDER, "oco_1").validation_result == "invalid"


def test_duffels_already_confirmed_error_means_already_rebooked(client, service):
    prepared(service)
    client.confirm_error = DuffelApiError(422, [{"type": "invalid_state_error", "code": "order_change_already_confirmed"}])
    with pytest.raises(AlreadyRebookedError):
        service.complete_rebooking(ORDER, "oco_1")


def test_a_dropped_connection_while_confirming_is_uncertain_not_a_failure(client, service):
    prepared(service)
    client.confirm_error = DuffelTransportError(httpx.ReadTimeout("x"), may_have_reached_duffel=True)
    with pytest.raises(DuffelTransportError) as exc:
        service.complete_rebooking(ORDER, "oco_1")
    assert not isinstance(exc.value, ServiceError)  # callers must treat it as pending
    assert service.get_confirmation(ORDER) is None


def test_mock_option_ids_never_reach_duffel(client, service):
    service.search_replacements(ORDER)
    with pytest.raises(UnknownOptionError):
        service.complete_rebooking(ORDER, "opt-1a")
    assert calls(client, "pending") == [] and calls(client, "confirm") == []


# --- airline changes and escalation ------------------------------------------------------------

def test_airline_changes_are_read_from_the_order(client, service):
    removed = [slice_([segment("2026-11-14T10:03:00", "2026-11-14T10:41:00")])]
    added = [slice_([segment("2026-11-14T11:03:00", "2026-11-14T11:41:00")])]
    client.order = order(changes=[{"id": "aic_1", "action_taken": None, "created_at": "2026-10-15T11:00:00Z",
                                   "removed": removed, "added": added}])
    (change,) = service.list_airline_changes(ORDER)
    assert change.change_id == "aic_1" and change.kind == "delay" and change.data_source == "duffel"
    assert change.summary == "The airline moved your departure from 10:03 AM on Nov 14 to 11:03 AM on Nov 14."
    assert calls(client, "get_order")  # reading the order, never Duffel's list call


def test_escalation_is_a_simulated_handoff(service):
    needs = Limits(budget_additional_cost=0, currency="USD", arrive_by="2026-10-15T15:00-07:00", max_connections=1, passenger_count=1)
    handoff = service.escalate_to_support(ORDER, "No option fits.", needs)
    assert handoff.case_id.startswith("SUP-") and len(handoff.case_id) == 10  # a ticket-style reference, no order id
    assert handoff.booking_details["simulated"] is True
    assert handoff.booking_details["data_source"] == "duffel" and "SIMULATED" in handoff.booking_details["label"]
