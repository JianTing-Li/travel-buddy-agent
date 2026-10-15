"""Probe script: finds which Duffel test-mode airline-change and order-change calls work. Owner: Jian.

Run from the repo root (token comes from DUFFEL_ACCESS_TOKEN, loaded by config.py):

    python -m backend.app.services.duffel.probe                    # search + list calls only
    python -m backend.app.services.duffel.probe --create-orders    # also create test orders, order change
                                                                   # requests/offers and pending changes
    python -m backend.app.services.duffel.probe --create-orders --confirm-change
                                                                   # also confirm a change and repeat it

The script refuses to run unless the token starts with "duffel_test_". It prints only
status codes, error fields, field names, types and a few allow-listed facts. It never
prints the token or passenger data, and passengers it creates use obviously fake details.
Endpoints marked "candidate" in the output are not confirmed by Duffel's docs.
"""
import argparse
import json
import sys
from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from ... import config

BASE_URL = "https://api.duffel.com"
TEST_TOKEN_PREFIX = "duffel_test_"
TEST_AIRLINE_IATA = "ZZ"  # Duffel Airways, the documented test-mode airline
TIMEOUT_SECONDS = 60.0
MAX_ERROR_MESSAGE_CHARS = 200
CHANGE_DATE_OFFSETS = (1, 2, 3)  # days after the original departure to try for replacements


def shape(value: Any, depth: int = 0) -> Any:
    """Describe a JSON value by field names and types only, never by content."""
    if depth > 5:
        return "..."
    if isinstance(value, dict):
        return {key: shape(item, depth + 1) for key, item in value.items()}
    if isinstance(value, list):
        return {"list_len": len(value), "item": shape(value[0], depth + 1) if value else None}
    return type(value).__name__


class Probe:
    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.results: list[dict] = []
        self.ctx: dict[str, Any] = {}

    def skip(self, step: str, reason: str) -> None:
        self.results.append({"step": step, "verdict": "skipped", "reason": reason})

    def call(
        self,
        step: str,
        method: str,
        path: str,
        *,
        template: str | None = None,
        params: dict | None = None,
        body: dict | None = None,
        facts: Any = None,
        candidate: bool = False,
    ) -> Any:
        """Make one request, record the outcome, and return the response `data` on success."""
        record: dict[str, Any] = {"step": step, "method": method, "path": template or path}
        if candidate:
            record["note"] = "candidate endpoint, not confirmed by Duffel docs"
        try:
            response = self.client.request(
                method, path, params=params, json={"data": body} if body is not None else None
            )
        except httpx.HTTPError as exc:
            record.update(verdict="error", error=type(exc).__name__)
            self.results.append(record)
            return None
        try:
            payload = response.json()
        except ValueError:
            payload = None
        record["status"] = response.status_code
        rate_limit = {k: v for k, v in response.headers.items() if k.lower().startswith("ratelimit")}
        if rate_limit:
            record["rate_limit_headers"] = rate_limit
        if response.is_success and isinstance(payload, dict) and "data" in payload:
            data = payload["data"]
            record["verdict"] = "worked"
            record["shape"] = shape(data)
            if facts:
                record["facts"] = facts(data)
            self.results.append(record)
            return data
        errors = payload.get("errors", []) if isinstance(payload, dict) else []
        record["verdict"] = "failed" if not response.is_success else "unexpected_body"
        record["errors"] = [
            {
                "type": e.get("type"),
                "code": e.get("code"),
                "title": e.get("title"),
                "message": str(e.get("message", ""))[:MAX_ERROR_MESSAGE_CHARS],
            }
            for e in errors
            if isinstance(e, dict)
        ]
        self.results.append(record)
        return None

    # --- search and order creation -------------------------------------------------

    def search(self, passengers: int, origin: str, destination: str, depart: date, key: str | None = None) -> None:
        key = key or f"{passengers}pax"
        step = f"offer_request_{key}"
        body = {
            "slices": [{"origin": origin, "destination": destination, "departure_date": depart.isoformat()}],
            "passengers": [{"type": "adult"} for _ in range(passengers)],
            "cabin_class": "economy",
        }

        def facts(data: dict) -> dict:
            offers = data.get("offers", [])
            owners = sorted({o.get("owner", {}).get("iata_code") for o in offers})
            return {
                "offer_count": len(offers),
                "owner_iata_codes": owners,
                "test_airline_offers": sum(1 for o in offers if o.get("owner", {}).get("iata_code") == TEST_AIRLINE_IATA),
                "segments_per_offer": sorted({len((o.get("slices") or [{}])[0].get("segments", [])) for o in offers}),
                "live_mode": data.get("live_mode"),
            }

        data = self.call(
            step,
            "POST",
            "/air/offer_requests",
            params={"return_offers": "true", "supplier_timeout": 30000},
            body=body,
            facts=facts,
        )
        if not data:
            return
        # Book only with the Duffel test airline, never an external airline sandbox.
        offers = [o for o in data.get("offers", []) if o.get("owner", {}).get("iata_code") == TEST_AIRLINE_IATA]
        if offers:
            offer = min(offers, key=lambda o: float(o["total_amount"]))
            self.ctx[f"search:{key}"] = {"offer": offer, "passenger_ids": [p["id"] for p in data["passengers"]]}

    def create_order(self, passengers: int, key: str | None = None) -> None:
        key = key or f"{passengers}pax"
        step = f"create_order_{key}"
        found = self.ctx.get(f"search:{key}")
        if not found:
            return self.skip(step, f"no {TEST_AIRLINE_IATA} offer from the {key} search")
        offer = found["offer"]
        body = {
            "selected_offers": [offer["id"]],
            "payments": [{"type": "balance", "currency": offer["total_currency"], "amount": offer["total_amount"]}],
            "passengers": [
                {
                    "id": passenger_id,
                    "title": "mr",
                    "gender": "m",
                    "given_name": "Test",
                    "family_name": f"Traveler{chr(64 + index)}",  # letters only: Duffel rejects digits in names
                    "born_on": "1990-01-01",
                    "email": f"test.traveler{index}@example.com",
                    "phone_number": "+442080160509",
                }
                for index, passenger_id in enumerate(found["passenger_ids"], start=1)
            ],
        }
        data = self.call(step, "POST", "/air/orders", body=body, facts=order_facts)
        if data:
            self.ctx[f"order:{key}"] = data

    def get_order(self, key: str, label: str) -> None:
        step = f"get_order_{key}_{label}"
        order = self.ctx.get(f"order:{key}")
        if not order:
            return self.skip(step, "no test order was created")
        data = self.call(step, "GET", f"/air/orders/{order['id']}", template="/air/orders/{id}", facts=order_facts)
        if data:
            self.ctx[f"order:{key}"] = data

    # --- airline-initiated changes ---------------------------------------------------

    def airline_changes(self, confirm: bool) -> None:
        def facts(data: list) -> dict:
            return {
                "count": len(data),
                "available_actions": [c.get("available_actions") for c in data[:5]],
                "action_taken": [c.get("action_taken") for c in data[:5]],
            }

        listed = self.call("list_airline_initiated_changes", "GET", "/air/airline_initiated_changes", facts=facts)
        order = self.ctx.get("order:1pax")
        if order:
            filtered = self.call(
                "list_airline_initiated_changes_for_order",
                "GET",
                "/air/airline_initiated_changes",
                template="/air/airline_initiated_changes?order_id={id}",
                params={"order_id": order["id"]},
                facts=facts,
            )
            listed = filtered or listed
        else:
            self.skip("list_airline_initiated_changes_for_order", "no test order was created")
        if not listed:
            self.skip("get_airline_initiated_change", "no airline-initiated changes exist to fetch")
            self.skip("accept_airline_initiated_change", "no airline-initiated changes exist to accept")
            return
        change_id = listed[0]["id"]
        self.call(
            "get_airline_initiated_change",
            "GET",
            f"/air/airline_initiated_changes/{change_id}",
            template="/air/airline_initiated_changes/{id}",
            candidate=True,
        )
        if confirm:
            self.call(
                "accept_airline_initiated_change",
                "POST",
                f"/air/airline_initiated_changes/{change_id}/actions/accept",
                template="/air/airline_initiated_changes/{id}/actions/accept",
                candidate=True,
            )
        else:
            self.skip("accept_airline_initiated_change", "needs --confirm-change")

    # --- scenarios from Duffel's "Test your integration" page ------------------------

    def airline_change_scenario(self, depart: date, confirm: bool) -> None:
        """LHR to LTN: Duffel says listing the changes of an order on this route creates a fake one."""
        key = "ltn"
        steps = ("list_airline_initiated_changes_ltn_call1", "list_airline_initiated_changes_ltn_call2",
                 "get_airline_initiated_change_ltn", "accept_airline_initiated_change_ltn")
        self.search(1, "LHR", "LTN", depart, key=key)
        self.create_order(1, key=key)
        order = self.ctx.get(f"order:{key}")
        if not order:
            for step in steps:
                self.skip(step, "no test order was created")
            return
        listed: list = []
        for call in (1, 2):  # Duffel says a new change is created on each call
            listed = self.call(
                f"list_airline_initiated_changes_{key}_call{call}",
                "GET",
                "/air/airline_initiated_changes",
                template="/air/airline_initiated_changes?order_id={id}",
                params={"order_id": order["id"]},
                facts=changes_facts,
            ) or listed
        self.get_order(key, "after_listing")
        if not listed:
            self.skip(f"get_airline_initiated_change_{key}", "listing returned no changes")
            self.skip(f"accept_airline_initiated_change_{key}", "listing returned no changes")
            return
        # Duffel rejects accepting anything but the latest change, and the list is oldest first.
        change_id = listed[-1]["id"]
        self.call(
            f"get_airline_initiated_change_{key}",
            "GET",
            f"/air/airline_initiated_changes/{change_id}",
            template="/air/airline_initiated_changes/{id}",
            candidate=True,
            facts=change_summary,
        )
        if not confirm:
            return self.skip(f"accept_airline_initiated_change_{key}", "needs --confirm-change")
        self.call(
            f"accept_airline_initiated_change_{key}",
            "POST",
            f"/air/airline_initiated_changes/{change_id}/actions/accept",
            template="/air/airline_initiated_changes/{id}/actions/accept",
            candidate=True,
            facts=change_summary,
        )
        self.call(
            f"list_airline_initiated_changes_{key}_after_accept",
            "GET",
            "/air/airline_initiated_changes",
            template="/air/airline_initiated_changes?order_id={id}",
            params={"order_id": order["id"]},
            facts=changes_facts,
        )
        self.get_order(key, "after_accept")

    def connections_scenario(self, depart: date) -> None:
        """LHR to DXB: Duffel says every offer has more than one segment."""
        key = "dxb"
        self.search(1, "LHR", "DXB", depart, key=key)
        self.create_order(1, key=key)
        self.order_change(key, confirm=False)

    def offer_scenario(self, key: str, origin: str, destination: str, depart: date) -> None:
        """Routes where Duffel says the offer's price changes (LHR to STN) or the offer has expired (LGW to LHR)."""
        self.search(1, origin, destination, depart, key=key)
        found = self.ctx.get(f"search:{key}")
        if not found:
            self.skip(f"get_offer_{key}", f"no {TEST_AIRLINE_IATA} offer from the {key} search")
            self.skip(f"create_order_{key}", f"no {TEST_AIRLINE_IATA} offer from the {key} search")
            return
        searched = found["offer"]

        def facts(latest: dict) -> dict:
            expires_at = latest.get("expires_at")
            return {
                "search_total_amount": searched.get("total_amount"),
                "latest_total_amount": latest.get("total_amount"),
                "total_currency": latest.get("total_currency"),
                "price_changed": latest.get("total_amount") != searched.get("total_amount"),
                "expires_at_in_past": bool(expires_at) and
                datetime.fromisoformat(expires_at.replace("Z", "+00:00")) < datetime.now(timezone.utc),
            }

        latest = self.call(f"get_offer_{key}", "GET", f"/air/offers/{searched['id']}", template="/air/offers/{id}", facts=facts)
        if latest:
            found["offer"] = latest  # book at the latest price, not the stale searched one
        self.create_order(1, key=key)

    # --- order changes ------------------------------------------------------------------

    def order_change(self, tag: str, confirm: bool, payment_first: bool = True) -> None:
        order = self.ctx.get(f"order:{tag}")
        if not order:
            for step in ("create_order_change_request", "list_order_change_offers", "get_order_change_offer",
                         "create_pending_order_change", "confirm_order_change", "confirm_order_change_again"):
                self.skip(f"{step}_{tag}", "no test order was created")
            return

        slice_ = order["slices"][0]
        departs = datetime.fromisoformat(slice_["segments"][0]["departing_at"]).date()
        offers: list = []
        for offset in CHANGE_DATE_OFFSETS:
            request_body = {
                "order_id": order["id"],
                "slices": {
                    "remove": [{"slice_id": slice_["id"]}],
                    "add": [
                        {
                            "origin": slice_["origin"]["iata_code"],
                            "destination": slice_["destination"]["iata_code"],
                            "departure_date": (departs + timedelta(days=offset)).isoformat(),
                            "cabin_class": "economy",
                        }
                    ],
                },
            }
            request = self.call(
                f"create_order_change_request_{tag}_plus{offset}d",
                "POST",
                "/air/order_change_requests",
                body=request_body,
                facts=change_request_facts,
            )
            offers = (request or {}).get("order_change_offers", [])
            if offers:
                request_id = request["id"]
                break
        if not offers:
            for step in ("list_order_change_offers", "get_order_change_offer", "create_pending_order_change",
                         "confirm_order_change", "confirm_order_change_again"):
                self.skip(f"{step}_{tag}", "order change request returned no offers")
            return

        self.call(
            f"list_order_change_offers_{tag}",
            "GET",
            "/air/order_change_offers",
            params={"order_change_request_id": request_id, "sort": "change_total_amount"},
            facts=list_offers_facts,
        )
        offer_id = offers[0]["id"]
        self.call(
            f"get_order_change_offer_{tag}",
            "GET",
            f"/air/order_change_offers/{offer_id}",
            template="/air/order_change_offers/{id}",
            facts=offer_facts,
        )
        pending = self.call(
            f"create_pending_order_change_{tag}",
            "POST",
            "/air/order_changes",
            body={"selected_order_change_offer": offer_id},
            facts=order_change_facts,
        )
        if not pending:
            for step in ("confirm_order_change", "confirm_order_change_again"):
                self.skip(f"{step}_{tag}", "no pending order change was created")
            return
        if not confirm:
            for step in ("confirm_order_change", "confirm_order_change_again"):
                self.skip(f"{step}_{tag}", "needs --confirm-change")
            return

        # Duffel says no payment is needed when the change total is zero or negative. To learn whether a
        # positive total still needs one, the 1-passenger order confirms with a payment and the
        # 3-passenger order tries without, falling back to a payment if that is rejected.
        amount = pending.get("change_total_amount")
        payment = {"payment": {"type": "balance", "currency": pending["change_total_currency"], "amount": amount}}
        confirm_path = f"/air/order_changes/{pending['id']}/actions/confirm"
        confirm_template = "/air/order_changes/{id}/actions/confirm"
        if payment_first:
            confirmed = self.call(f"confirm_order_change_{tag}_with_payment", "POST", confirm_path,
                                  template=confirm_template, body=payment, facts=order_change_facts)
        else:
            confirmed = self.call(f"confirm_order_change_{tag}_no_payment", "POST", confirm_path,
                                  template=confirm_template, body={}, facts=order_change_facts)
            if not confirmed:
                confirmed = self.call(f"confirm_order_change_{tag}_with_payment", "POST", confirm_path,
                                      template=confirm_template, body=payment, facts=order_change_facts)
        self.call(f"confirm_order_change_again_{tag}", "POST", confirm_path, template=confirm_template,
                  body=payment, facts=order_change_facts)
        self.get_order(tag, "after_change")
        self.second_change(tag)

    def second_change(self, tag: str) -> None:
        """Try to change the same order again, to learn whether Duffel Airways allows repeat changes."""
        order = self.ctx[f"order:{tag}"]
        slice_ = order["slices"][0]
        departs = datetime.fromisoformat(slice_["segments"][0]["departing_at"]).date()
        self.call(
            f"create_order_change_request_{tag}_second_change",
            "POST",
            "/air/order_change_requests",
            body={
                "order_id": order["id"],
                "slices": {
                    "remove": [{"slice_id": slice_["id"]}],
                    "add": [{
                        "origin": slice_["origin"]["iata_code"],
                        "destination": slice_["destination"]["iata_code"],
                        "departure_date": (departs + timedelta(days=1)).isoformat(),
                        "cabin_class": "economy",
                    }],
                },
            },
            facts=change_request_facts,
        )


def order_facts(data: dict) -> dict:
    return {
        "live_mode": data.get("live_mode"),
        "type": data.get("type"),
        "available_actions": data.get("available_actions"),
        "passenger_count": len(data.get("passengers", [])),
        "slice_count": len(data.get("slices", [])),
        "slice_ids": [s.get("id") for s in data.get("slices", [])],
        "total_currency": data.get("total_currency"),
        "owner_iata_code": data.get("owner", {}).get("iata_code"),
        "airline_initiated_changes": len(data.get("airline_initiated_changes") or []),
        "changes": len(data.get("changes") or []),
    }


def offer_facts(offer: dict) -> dict:
    return {
        "change_total_amount": offer.get("change_total_amount"),
        "change_total_currency": offer.get("change_total_currency"),
        "penalty_total_amount": offer.get("penalty_total_amount"),
        "penalty_total_currency": offer.get("penalty_total_currency"),
        "new_total_amount": offer.get("new_total_amount"),
        "new_total_currency": offer.get("new_total_currency"),
        "refund_to": offer.get("refund_to"),
        "has_expires_at": bool(offer.get("expires_at")),
        "condition_keys": sorted((offer.get("conditions") or {}).keys()),
    }


def change_summary(change: dict) -> dict:
    """Describe an airline-initiated change by actions and segment timing, without passenger data."""
    def side(name: str) -> dict:
        segments = [seg for sl in change.get(name) or [] for seg in sl.get("segments", [])]
        return {
            "segments": len(segments),
            "first_departing_at": segments[0].get("departing_at") if segments else None,
            "last_arriving_at": segments[-1].get("arriving_at") if segments else None,
        }

    return {
        "available_actions": change.get("available_actions"),
        "action_taken": change.get("action_taken"),
        "removed": side("removed"),
        "added": side("added"),
        "has_travel_agent_ticket": change.get("travel_agent_ticket") is not None,
    }


def changes_facts(changes: list) -> dict:
    return {"count": len(changes), "changes": [change_summary(c) for c in changes[:5]]}


def list_offers_facts(offers: list) -> dict:
    """Summarise how replacement offers differ: cost, connections and timing."""
    def added(offer: dict) -> dict:
        slice_ = (offer.get("slices", {}).get("add") or [{}])[0]
        segments = slice_.get("segments", [])
        return {
            "segments": len(segments),
            "departing_at": segments[0].get("departing_at") if segments else None,
            "arriving_at": segments[-1].get("arriving_at") if segments else None,
            "duration": slice_.get("duration"),
        }

    return {
        "count": len(offers),
        "distinct_change_total_amounts": sorted({o.get("change_total_amount") for o in offers}),
        "distinct_penalty_total_amounts": sorted({o.get("penalty_total_amount") for o in offers}),
        "distinct_new_total_amounts": sorted({o.get("new_total_amount") for o in offers}),
        "distinct_change_currencies": sorted({o.get("change_total_currency") for o in offers}),
        "distinct_refund_to": sorted({str(o.get("refund_to")) for o in offers}),
        "change_before_departure_allowed": sorted({str((o.get("conditions") or {}).get("change_before_departure", {}).get("allowed")) for o in offers}),
        "offers": [added(o) for o in offers],
    }


def change_request_facts(data: dict) -> dict:
    offers = data.get("order_change_offers", [])
    return {"offer_count": len(offers), "first_offer": offer_facts(offers[0]) if offers else None}


def order_change_facts(data: dict) -> dict:
    return {
        "change_total_amount": data.get("change_total_amount"),
        "change_total_currency": data.get("change_total_currency"),
        "penalty_total_amount": data.get("penalty_total_amount"),
        "refund_to": data.get("refund_to"),
        "has_expires_at": bool(data.get("expires_at")),
        "confirmed_at_set": data.get("confirmed_at") is not None,
        "live_mode": data.get("live_mode"),
    }


SCENARIOS = {
    "airline-change": lambda probe, depart, confirm: probe.airline_change_scenario(depart, confirm),
    "connections": lambda probe, depart, confirm: probe.connections_scenario(depart),
    "price-change": lambda probe, depart, confirm: probe.offer_scenario("stn", "LHR", "STN", depart),
    "expired-offer": lambda probe, depart, confirm: probe.offer_scenario("lhr", "LGW", "LHR", depart),
}


def run(args: argparse.Namespace) -> int:
    token = config.DUFFEL_ACCESS_TOKEN
    if not token:
        print("DUFFEL_ACCESS_TOKEN is not set. Add it to .env or the environment.", file=sys.stderr)
        return 1
    if not token.startswith(TEST_TOKEN_PREFIX):
        print(f"Refusing to run: the token does not start with {TEST_TOKEN_PREFIX!r}.", file=sys.stderr)
        return 1

    headers = {
        "Authorization": f"Bearer {token}",
        "Duffel-Version": "v2",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    depart = date.today() + timedelta(days=args.days_ahead)
    if args.scenario and not args.create_orders:
        print("--scenario creates test orders, so it also needs --create-orders.", file=sys.stderr)
        return 1
    with httpx.Client(base_url=BASE_URL, headers=headers, timeout=TIMEOUT_SECONDS) as client:
        probe = Probe(client)
        if args.scenario:
            names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
            for name in names:
                SCENARIOS[name](probe, depart, args.confirm_change)
            return finish(probe, "scenarios: " + ", ".join(names), depart, args.out)
        for passengers in (1, 3):
            probe.search(passengers, args.origin, args.destination, depart)
        if args.create_orders:
            for passengers in (1, 3):
                probe.create_order(passengers)
                probe.get_order(f"{passengers}pax", "fresh")
        else:
            for passengers in (1, 3):
                probe.skip(f"create_order_{passengers}pax", "needs --create-orders")
        probe.airline_changes(args.confirm_change)
        if args.create_orders:
            for passengers in (1, 3):
                probe.order_change(f"{passengers}pax", args.confirm_change, payment_first=passengers == 1)
        else:
            probe.skip("order_change_flow", "needs --create-orders")

    return finish(probe, f"{args.origin}-{args.destination}", depart, args.out)


def finish(probe: Probe, route: str, depart: date, out: str | None) -> int:
    for result in probe.results:
        status = result.get("status", "-")
        print(f"{result['verdict']:<10} {status!s:<5} {result['step']}")
    report = json.dumps({"route": route, "departure_date": depart.isoformat(), "results": probe.results}, indent=2)
    if out:
        with open(out, "w") as handle:
            handle.write(report)
        print(f"Full report written to {out}")
    else:
        print(report)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Probe Duffel test-mode order-change support.")
    parser.add_argument("--origin", default="JFK")
    parser.add_argument("--destination", default="LAX")
    parser.add_argument("--days-ahead", type=int, default=30)
    parser.add_argument("--create-orders", action="store_true", help="create test orders and pending order changes")
    parser.add_argument("--confirm-change", action="store_true", help="confirm order changes and accept airline changes")
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"],
                        help="run a test scenario from Duffel's docs instead of the standard flow (needs --create-orders)")
    parser.add_argument("--out", help="write the JSON report to this path instead of stdout")
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
