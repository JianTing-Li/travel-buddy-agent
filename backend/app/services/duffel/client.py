"""Duffel test API client (sync). Owner: Jian.

Covers only the calls the probe verified in test mode (see docs/duffel-notes.md). Every method
returns {"data_source": "duffel", "data": <Duffel's response data, unchanged>}. The client never
maps to contract models, never fills in an unknown eligibility or cost, and never retries.
Mapping and limit checks belong to the tools and the harness.

Untested in test mode, so not included: fetching, accepting or updating an airline-initiated change.
"""
from typing import Any

import httpx

from ... import config
from ...contract.models import DataSource

BASE_URL = "https://api.duffel.com"
DATA_SOURCE: DataSource = "duffel"
TEST_TOKEN_PREFIX = "duffel_test_"
TIMEOUT_SECONDS = 60.0
SEARCH_SUPPLIER_TIMEOUT_MS = 30000
MAX_ERROR_MESSAGE_CHARS = 200


class DuffelError(Exception):
    """Base class for every error this client raises."""


class DuffelConfigError(DuffelError):
    """The token is missing or is not a Duffel test-mode token."""


class DuffelApiError(DuffelError):
    """Duffel answered with an error status or an unexpected body."""

    def __init__(self, status: int, errors: list[dict[str, str | None]]) -> None:
        self.status = status
        self.errors = errors
        detail = "; ".join(f"{e.get('type')}/{e.get('code')}: {e.get('message')}" for e in errors) or "no error body"
        super().__init__(f"Duffel returned {status}: {detail}")

    @property
    def codes(self) -> list[str | None]:
        return [e.get("code") for e in self.errors]


class DuffelTransportError(DuffelError):
    """The request failed before a response arrived.

    may_have_reached_duffel is False only when the connection was never made. Otherwise the call
    may have succeeded, so a write must be checked (for example by fetching the order) before it is retried.
    """

    def __init__(self, cause: httpx.HTTPError, may_have_reached_duffel: bool) -> None:
        self.may_have_reached_duffel = may_have_reached_duffel
        super().__init__(f"Duffel request failed: {type(cause).__name__}")


def _tagged(data: Any) -> dict[str, Any]:
    return {"data_source": DATA_SOURCE, "data": data}


class DuffelClient:
    def __init__(self, token: str | None = None, *, http: httpx.Client | None = None) -> None:
        token = token if token is not None else config.DUFFEL_ACCESS_TOKEN
        if not token:
            raise DuffelConfigError("DUFFEL_ACCESS_TOKEN is not set")
        if not token.startswith(TEST_TOKEN_PREFIX):
            raise DuffelConfigError(f"Only Duffel test tokens are allowed (they start with {TEST_TOKEN_PREFIX!r})")
        self._http = http or httpx.Client(base_url=BASE_URL, timeout=TIMEOUT_SECONDS)
        self._owns_http = http is None
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Duffel-Version": "v2",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def close(self) -> None:
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> "DuffelClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _request(
        self, method: str, path: str, *, params: dict | None = None, body: dict | None = None
    ) -> dict[str, Any]:
        try:
            response = self._http.request(
                method, path, headers=self._headers, params=params,
                json={"data": body} if body is not None else None,
            )
        except httpx.HTTPError as exc:
            # A connect failure means nothing was sent; any other failure may have reached Duffel.
            raise DuffelTransportError(exc, may_have_reached_duffel=not isinstance(exc, httpx.ConnectError)) from None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        if response.is_success and isinstance(payload, dict) and "data" in payload:
            return _tagged(payload["data"])
        errors = payload.get("errors", []) if isinstance(payload, dict) else []
        raise DuffelApiError(
            response.status_code,
            [
                {
                    "type": e.get("type"),
                    "code": e.get("code"),
                    "title": e.get("title"),
                    "message": str(e.get("message", ""))[:MAX_ERROR_MESSAGE_CHARS],
                }
                for e in errors
                if isinstance(e, dict)
            ],
        )

    # --- search and test orders ---------------------------------------------------

    def search_offers(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        passengers: int = 1,
        cabin_class: str = "economy",
        max_connections: int | None = None,
    ) -> dict[str, Any]:
        """POST /air/offer_requests. `departure_date` is YYYY-MM-DD. Offers are in data["offers"]."""
        body: dict[str, Any] = {
            "slices": [{"origin": origin, "destination": destination, "departure_date": departure_date}],
            "passengers": [{"type": "adult"} for _ in range(passengers)],
            "cabin_class": cabin_class,
        }
        if max_connections is not None:
            body["max_connections"] = max_connections
        return self._request(
            "POST", "/air/offer_requests",
            params={"return_offers": "true", "supplier_timeout": SEARCH_SUPPLIER_TIMEOUT_MS}, body=body,
        )

    def create_test_order(
        self, offer_id: str, total_amount: str, total_currency: str, passengers: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """POST /air/orders, paid from the test balance. Each passenger needs the `id` from the offer request
        plus the name, born_on, gender, title, email and phone_number fields Duffel requires."""
        return self._request(
            "POST", "/air/orders",
            body={
                "selected_offers": [offer_id],
                "payments": [{"type": "balance", "currency": total_currency, "amount": total_amount}],
                "passengers": passengers,
            },
        )

    def get_order(self, order_id: str) -> dict[str, Any]:
        """GET /air/orders/{id}: itinerary, passengers, available_actions and airline_initiated_changes."""
        return self._request("GET", f"/air/orders/{order_id}")

    # --- airline-initiated changes ----------------------------------------------------

    def list_airline_initiated_changes(self, order_id: str | None = None) -> dict[str, Any]:
        """GET /air/airline_initiated_changes. data is a list, empty in test mode."""
        return self._request(
            "GET", "/air/airline_initiated_changes", params={"order_id": order_id} if order_id else None
        )

    # --- order changes -------------------------------------------------------------------

    def create_order_change_request(
        self,
        order_id: str,
        remove_slice_id: str,
        origin: str,
        destination: str,
        departure_date: str,
        cabin_class: str = "economy",
    ) -> dict[str, Any]:
        """POST /air/order_change_requests. Offers are in data["order_change_offers"]."""
        return self._request(
            "POST", "/air/order_change_requests",
            body={
                "order_id": order_id,
                "slices": {
                    "remove": [{"slice_id": remove_slice_id}],
                    "add": [{
                        "origin": origin,
                        "destination": destination,
                        "departure_date": departure_date,
                        "cabin_class": cabin_class,
                    }],
                },
            },
        )

    def list_order_change_offers(
        self, order_change_request_id: str, sort: str = "change_total_amount", max_connections: int | None = None
    ) -> dict[str, Any]:
        """GET /air/order_change_offers. data is a list. The additional cost is change_total_amount."""
        params: dict[str, Any] = {"order_change_request_id": order_change_request_id, "sort": sort}
        if max_connections is not None:
            params["max_connections"] = max_connections
        return self._request("GET", "/air/order_change_offers", params=params)

    def get_order_change_offer(self, offer_id: str) -> dict[str, Any]:
        """GET /air/order_change_offers/{id}: the latest cost, conditions and expires_at for one offer."""
        return self._request("GET", f"/air/order_change_offers/{offer_id}")

    def create_pending_order_change(self, offer_id: str) -> dict[str, Any]:
        """POST /air/order_changes. Creates a pending change; nothing changes on the order until confirmed."""
        return self._request("POST", "/air/order_changes", body={"selected_order_change_offer": offer_id})

    def confirm_order_change(
        self, order_change_id: str, change_total_amount: str, change_total_currency: str
    ) -> dict[str, Any]:
        """POST /air/order_changes/{id}/actions/confirm, paid from the test balance.

        Pass the pending change's own change_total_amount and currency exactly as Duffel returned them.
        Call only after the traveler confirmed. Duffel rejects a repeat with order_change_already_confirmed,
        and this client never retries: on DuffelTransportError check the order before trying again.
        """
        return self._request(
            "POST", f"/air/order_changes/{order_change_id}/actions/confirm",
            body={"payment": {"type": "balance", "currency": change_total_currency, "amount": change_total_amount}},
        )
