"""Duffel TEST bookings behind the same methods as MockService, mapped to the contract models. Owner: Jian.

Only Duffel test-mode orders (ids "ord_...") are handled, through DuffelClient, which refuses live tokens.
Mapping rules are PROVISIONAL until the contract is agreed (see docs/duffel-notes.md for what Duffel returns):
- additional_cost is change_total_amount in change_total_currency, never new_total_amount. A negative value is
  a refund and is passed through unchanged.
- eligibility is "eligible" only when the order's available_actions includes "change" and the offer's
  conditions.change_before_departure.allowed is true; otherwise "unknown", which blocks rebooking.
- validity is "valid" while the offer's expires_at is in the future, otherwise "expired".
- Replacement searches use the original departure date, then the next day if nothing came back. Each search
  creates an order change request in Duffel. Offers missing a cost or currency are dropped, and offers that
  repeat the same flight times and cost are shown once.
- Passenger names are not passed on: the agent only needs how many travel and their ids.
Escalation is the simulated support handoff, as for mock bookings. Completing a change uses Duffel's test
balance; a dropped connection while confirming is re-raised so callers treat the result as uncertain.
"""
import re
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from ...contract.models import Handoff, Limits, Option, TripContext, ValidationResult
from ..airline_change import AirlineChange
from ..errors import (
    AlreadyRebookedError,
    RebookingNotAllowedError,
    ServiceError,
    UnknownBookingError,
    UnknownOptionError,
)
from ..mock import provisional
from ..validation import clock_text, diff_options, validate_option
from .client import DuffelApiError, DuffelClient, DuffelTransportError

ORDER_PREFIX = "ord_"
HANDOFF_NOTE = "SIMULATED support handoff. No real staff will follow up."
CONFIRMATION_NOTE = "Completed through Duffel's TEST API. No real airline ticket was created or changed."
UNREACHABLE = "Duffel could not be reached. Try again shortly."


class DuffelServiceError(ServiceError):
    """Duffel refused or failed a call; the message carries only Duffel's error code."""


def _api_error(exc: DuffelApiError) -> DuffelServiceError:
    codes = ", ".join(c for c in exc.codes if c) or "no code"
    return DuffelServiceError(f"Duffel returned {exc.status} ({codes}).")


def _local(naive: str | None, zone: str | None) -> str | None:
    """Duffel gives local wall-clock times plus the airport's time zone; add the UTC offset."""
    if not naive:
        return None
    try:
        moment = datetime.fromisoformat(naive)
        if moment.tzinfo is None and zone:
            moment = moment.replace(tzinfo=ZoneInfo(zone))
        return moment.isoformat(timespec="minutes")
    except (ValueError, ZoneInfoNotFoundError):
        return naive


def _duration(iso: str | None) -> str | None:
    match = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?", iso or "")
    if not match or not any(match.groups()):
        return iso
    days, hours, minutes = (int(g or 0) for g in match.groups())
    return f"{days * 24 + hours}h {minutes}m"


def _segment_details(slice_: dict[str, Any]) -> dict[str, Any]:
    segments = slice_.get("segments") or []
    first, last = (segments[0], segments[-1]) if segments else ({}, {})
    carrier = first.get("marketing_carrier") or {}
    return {
        "airline": carrier.get("name"),
        "flight": f"{carrier.get('iata_code') or ''}{first.get('marketing_carrier_flight_number') or ''}" or None,
        "origin": (slice_.get("origin") or {}).get("iata_code"),
        "destination": (slice_.get("destination") or {}).get("iata_code"),
        "departs": _local(first.get("departing_at"), (first.get("origin") or {}).get("time_zone")),
        "arrives": _local(last.get("arriving_at"), (last.get("destination") or {}).get("time_zone")),
        "duration": _duration(slice_.get("duration")),
        "connections": max(len(segments) - 1, 0),
    }


class _Booking:
    def __init__(self, order_id: str) -> None:
        self.order_id = order_id
        self.offer_ids: list[str] = []  # offers this booking's searches returned; nothing else can be prepared
        self.seen: dict[str, Option] = {}
        self.prepared: tuple[str, Option] | None = None
        self.confirmation: dict[str, Any] | None = None
        self.handoffs: list[Handoff] = []


class DuffelService:
    def __init__(self, client: DuffelClient, now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)) -> None:
        self._client = client
        self._now = now
        self._lock = threading.RLock()
        self._bookings: dict[str, _Booking] = {}

    # --- bookings ------------------------------------------------------------------------

    def _call(self, fn: Callable[..., dict[str, Any]], *args: Any) -> Any:
        """A read or a request that changes nothing on its own; any failure is a ServiceError."""
        try:
            return fn(*args)["data"]
        except DuffelApiError as exc:
            if exc.status == 404:
                raise UnknownBookingError("Duffel test booking not found") from None
            raise _api_error(exc) from None
        except DuffelTransportError:
            raise DuffelServiceError(UNREACHABLE) from None

    def add_booking(self, order_id: str) -> str:
        """Track an existing Duffel TEST order. Returns its id."""
        if not isinstance(order_id, str) or not order_id.startswith(ORDER_PREFIX):
            raise UnknownBookingError("Only Duffel order ids (ord_...) can be added")
        order = self._call(self._client.get_order, order_id)
        if order.get("live_mode") is not False:
            raise ServiceError("Only Duffel test-mode orders can be used")
        with self._lock:
            self._bookings.setdefault(order_id, _Booking(order_id))
        return order_id

    def booking_ids(self) -> list[str]:
        return list(self._bookings)

    def _booking(self, booking_id: str) -> _Booking:
        try:
            return self._bookings[booking_id]
        except KeyError:
            raise UnknownBookingError(f"Duffel test booking '{booking_id}' is not tracked here") from None

    def _order(self, booking_id: str) -> dict[str, Any]:
        self._booking(booking_id)
        return self._call(self._client.get_order, booking_id)

    # --- trip context and airline changes --------------------------------------------------

    def get_trip_context(self, booking_id: str) -> TripContext:
        order = self._order(booking_id)
        slice_ = (order.get("slices") or [{}])[0]
        details = _segment_details(slice_)
        open_changes = [c for c in order.get("airline_initiated_changes") or [] if not c.get("action_taken")]
        with self._lock:
            rebooked = self._booking(booking_id).confirmation is not None
        if rebooked:
            status, disruption = "rebooked", {"type": "rebooked through Duffel test API"}
        elif order.get("cancelled_at"):
            status, disruption = "canceled", {"type": "order cancelled"}
        elif open_changes:
            status, disruption = "delayed", {"type": "airline schedule change", "open_changes": len(open_changes)}
        else:
            status, disruption = "on time", {"type": "none reported"}
        return TripContext(
            original_itinerary={
                "booking_id": booking_id,
                "flight": details["flight"],
                "airline": details["airline"],
                "origin": details["origin"],
                "destination": details["destination"],
                "departs": details["departs"],
                "arrives": details["arrives"],
                "status": status,
                "booking_reference": order.get("booking_reference"),
            },
            passengers=[{"passenger_id": p.get("id"), "type": p.get("type")} for p in order.get("passengers") or []],
            disruption_details={**disruption, "simulated": True, "test_mode": True},
            data_source="duffel",
        )

    def list_airline_changes(self, booking_id: str) -> list[AirlineChange]:
        """Read changes from the order itself. Duffel's list endpoint creates a new fake change on every call
        for LHR to LTN test orders, so it is not used for polling."""
        order = self._order(booking_id)
        changes = []
        for change in order.get("airline_initiated_changes") or []:
            before = _segment_details((change.get("removed") or [{}])[0])
            after = _segment_details((change.get("added") or [{}])[0])
            summary = "The airline changed this flight."
            if before["departs"] and after["departs"]:
                summary = (f"The airline moved the departure from {clock_text(datetime.fromisoformat(before['departs']))} "
                           f"to {clock_text(datetime.fromisoformat(after['departs']))}.")
            changes.append(AirlineChange(
                change_id=change.get("id") or "", booking_id=booking_id, kind="delay", summary=summary,
                detected_at=change.get("created_at") or self._now().isoformat(timespec="seconds"),
                data_source="duffel",
            ))
        return [c for c in changes if c.change_id]

    # --- replacements ---------------------------------------------------------------------

    def _option(self, offer: dict[str, Any], changeable: bool) -> Option | None:
        amount, currency = offer.get("change_total_amount"), offer.get("change_total_currency")
        if amount is None or not currency:
            return None
        try:
            cost = float(amount)
        except (TypeError, ValueError):
            return None
        conditions = (offer.get("conditions") or {}).get("change_before_departure") or {}
        eligible = changeable and conditions.get("allowed") is True
        expires = offer.get("expires_at")
        try:
            valid = bool(expires) and datetime.fromisoformat(expires.replace("Z", "+00:00")) > self._now()
        except ValueError:
            valid = False
        details = _segment_details(((offer.get("slices") or {}).get("add") or [{}])[0])
        return Option(
            option_id=offer.get("id") or "",
            flight_details={**details, "simulated": True, "test_mode": True},
            eligibility=provisional.ELIGIBLE if eligible else provisional.UNKNOWN,
            additional_cost=cost,
            currency=currency,
            validity=provisional.VALIDITY_VALID if valid else provisional.VALIDITY_EXPIRED,
            data_source="duffel",
        )

    def search_replacements(self, booking_id: str) -> list[Option]:
        order = self._order(booking_id)
        if "change" not in (order.get("available_actions") or []):
            raise RebookingNotAllowedError("Duffel does not allow changes to this test order (it may have been changed already).")
        slice_ = (order.get("slices") or [{}])[0]
        details = _segment_details(slice_)
        if not (slice_.get("id") and details["origin"] and details["destination"] and details["departs"]):
            raise DuffelServiceError("The Duffel order is missing the flight details needed to search.")
        start = date.fromisoformat(details["departs"][:10])
        options: list[Option] = []
        for day in (start, start + timedelta(days=1)):
            request = self._call(
                self._client.create_order_change_request,
                booking_id, slice_["id"], details["origin"], details["destination"], day.isoformat(),
            )
            mapped = [self._option(o, changeable=True) for o in request.get("order_change_offers") or []]
            options = [o for o in mapped if o is not None and o.option_id]
            if options:
                break
        unique: dict[tuple[Any, ...], Option] = {}
        for option in options:
            d = option.flight_details
            unique.setdefault((d["departs"], d["arrives"], d["connections"], option.additional_cost, option.currency), option)
        result = list(unique.values())
        with self._lock:
            booking = self._booking(booking_id)
            booking.offer_ids = [o.option_id for o in result]
            for option in result:
                booking.seen[option.option_id] = option.model_copy(deep=True)
        return [o.model_copy(deep=True) for o in result]

    def get_option(self, booking_id: str, option_id: str) -> Option:
        """The offer as Duffel reports it right now. Only offers this booking's own searches returned."""
        with self._lock:
            if option_id not in self._booking(booking_id).offer_ids:
                raise UnknownOptionError(f"Option '{option_id}' not found for this booking")
        order = self._order(booking_id)
        offer = self._call(self._client.get_order_change_offer, option_id)
        option = self._option(offer, changeable="change" in (order.get("available_actions") or []))
        if option is None:
            raise DuffelServiceError("Duffel did not return a cost for this option.")
        return option

    def prepare_rebooking(self, booking_id: str, option_id: str) -> ValidationResult:
        latest = self.get_option(booking_id, option_id)
        with self._lock:
            booking = self._booking(booking_id)
            if booking.confirmation is not None:
                return ValidationResult(latest_option_details=latest, validation_result=provisional.RESULT_INVALID,
                                        changes_to_review=["This booking was already rebooked through Duffel's test API."])
            result, reasons = validate_option(latest)
            if result != provisional.RESULT_VALID:
                booking.prepared = None
                return ValidationResult(latest_option_details=latest, validation_result=result, changes_to_review=reasons)
            seen = booking.seen.get(option_id)
            changes = diff_options(seen, latest) if seen is not None else []
            booking.seen[option_id] = latest.model_copy(deep=True)
            if changes:
                booking.prepared = None
                return ValidationResult(latest_option_details=latest, validation_result=provisional.RESULT_CHANGED,
                                        changes_to_review=changes)
            booking.prepared = (option_id, latest.model_copy(deep=True))
            return ValidationResult(latest_option_details=latest, validation_result=provisional.RESULT_VALID,
                                    changes_to_review=[])

    def complete_rebooking(self, booking_id: str, option_id: str) -> dict[str, Any]:
        """Confirm the change through Duffel's TEST API. Call only after the traveler explicitly confirmed."""
        latest = self.get_option(booking_id, option_id)
        with self._lock:
            booking = self._booking(booking_id)
            if booking.confirmation is not None:
                raise AlreadyRebookedError("This booking was already rebooked through Duffel's test API")
            result, reasons = validate_option(latest)
            if result != provisional.RESULT_VALID:
                raise RebookingNotAllowedError(" ".join(reasons))
            if booking.prepared is None or booking.prepared[0] != option_id:
                raise RebookingNotAllowedError("This option was not prepared and reviewed first.")
            if diff_options(booking.prepared[1], latest):
                raise RebookingNotAllowedError("This option changed after it was prepared and needs a new review.")
            reviewed = booking.prepared[1]

            pending = self._call(self._client.create_pending_order_change, option_id)
            pending_cost = pending.get("change_total_amount")
            if (pending_cost is None or float(pending_cost) != reviewed.additional_cost
                    or pending.get("change_total_currency") != reviewed.currency):
                booking.prepared = None
                raise RebookingNotAllowedError("Duffel quoted a different cost when booking. Review the option again.")
            try:
                confirmed = self._client.confirm_order_change(
                    pending["id"], pending_cost, pending["change_total_currency"])["data"]
            except DuffelApiError as exc:
                if "order_change_already_confirmed" in exc.codes:
                    raise AlreadyRebookedError("Duffel says this change was already confirmed") from None
                raise _api_error(exc) from None
            # DuffelTransportError is not caught on purpose: the change may have gone through, so it is uncertain.

            booking.confirmation = {
                "confirmation_id": confirmed.get("id") or pending["id"],
                "simulated": True,
                "data_source": "duffel",
                "note": CONFIRMATION_NOTE,
                "booking_id": booking_id,
                "option_id": option_id,
                "additional_cost": reviewed.additional_cost,
                "currency": reviewed.currency,
                "updated_itinerary": dict(reviewed.flight_details),
            }
            booking.prepared = None
            return dict(booking.confirmation)

    def get_confirmation(self, booking_id: str) -> dict[str, Any] | None:
        with self._lock:
            confirmation = self._booking(booking_id).confirmation
            return dict(confirmation) if confirmation else None

    def escalate_to_support(self, booking_id: str, unresolved_issue: str, confirmed_needs: Limits) -> Handoff:
        """SIMULATED handoff, as for mock bookings. Booking details are read from the order if Duffel answers."""
        try:
            trip = self.get_trip_context(booking_id)
            booking_details = {**trip.original_itinerary, "passenger_count": len(trip.passengers)}
        except DuffelServiceError:
            booking_details = {"booking_id": booking_id, "note": "Duffel could not be reached for the details."}
        handoff = Handoff(
            case_id=f"SIM-{booking_id}",
            booking_details={**booking_details, "data_source": "duffel", "simulated": True, "label": HANDOFF_NOTE},
            confirmed_needs=confirmed_needs,
            unresolved_issue=unresolved_issue,
        )
        with self._lock:
            self._booking(booking_id).handoffs.append(handoff)
        return handoff.model_copy(deep=True)
