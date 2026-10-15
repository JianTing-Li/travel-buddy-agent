"""Clearly labeled MOCK service for replacements, validation and confirmation. Owner: Jian.

Everything here is simulated: nothing is sent to Duffel and no real ticket is created. The service holds bookings
in memory (loaded from data/mock/scenarios/) and returns contract models unchanged, all tagged data_source="mock".

It is the mock side of the tools in PRD 3a:
  get_trip_context, search_replacements, prepare_rebooking, escalate_to_support, plus complete_rebooking, which
  application code calls only after the traveler explicitly confirmed.
It never filters by the traveler's limits (the harness does that) and never decides what to recommend.

Safety rules enforced here, as the mock "validation and confirmation service":
- Duffel-looking ids are rejected, so a Duffel booking is never handled by the mock.
- Unknown eligibility or an unavailable option blocks rebooking.
- complete_rebooking needs a prepare_rebooking of the same option first, refuses if the option changed since,
  and runs at most once per booking.
"""
import threading
from datetime import date
from typing import Any

from ...contract.models import Handoff, Limits, Option, TripContext, ValidationResult
from . import provisional
from .scenarios import Scenario, load_scenario, scenario_names

DUFFEL_ID_PREFIXES = ("ord_", "off_", "orq_", "oco_", "ocr_", "ocg_", "aic_", "sli_", "pas_")
SIMULATED_NOTE = "SIMULATED rebooking. No real airline ticket was created and nothing was sent to Duffel."
HANDOFF_NOTE = "SIMULATED support handoff. No real staff will follow up."


class MockServiceError(Exception):
    """Base class for errors the mock service raises."""


class UnknownBookingError(MockServiceError):
    pass


class UnknownOptionError(MockServiceError):
    pass


class RebookingNotAllowedError(MockServiceError):
    """The option failed validation, was not prepared, or changed since it was prepared."""


class AlreadyRebookedError(MockServiceError):
    """This booking already has a simulated rebooking."""


class _Booking:
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.options: dict[str, Option] = {o.option_id: o.model_copy(deep=True) for o in scenario.options}
        self.seen: dict[str, Option] = {}  # option as last shown to the traveler (search or prepare)
        self.prepared: tuple[str, Option] | None = None  # (option_id, option as prepared)
        self.confirmation: dict[str, Any] | None = None
        self.handoffs: list[Handoff] = []


def _validate(option: Option) -> tuple[str, list[str]]:
    """Return (validation_result, reasons) from the option's own eligibility and validity."""
    if option.eligibility == provisional.INELIGIBLE:
        return provisional.RESULT_INVALID, ["This option is not eligible for this booking."]
    if option.eligibility != provisional.ELIGIBLE:
        return provisional.RESULT_INVALID, ["Eligibility could not be verified for this option."]
    if option.validity == provisional.VALIDITY_EXPIRED:
        return provisional.RESULT_UNAVAILABLE, ["This option has expired."]
    if option.validity == provisional.VALIDITY_UNAVAILABLE:
        return provisional.RESULT_UNAVAILABLE, ["This option is no longer available."]
    if option.validity != provisional.VALIDITY_VALID:
        return provisional.RESULT_INVALID, ["The status of this option could not be verified."]
    return provisional.RESULT_VALID, []


_DETAIL_LABELS = {
    "departs": "Departure time", "arrives": "Arrival time", "duration": "Duration",
    "connections": "Connections", "flight": "Flight", "origin": "Origin", "destination": "Destination",
}


def _diff(old: Option, new: Option) -> list[str]:
    """Human-readable differences the traveler must review."""
    changes = []
    if old.additional_cost != new.additional_cost or old.currency != new.currency:
        changes.append(f"Additional cost changed from {old.additional_cost:g} {old.currency} "
                       f"to {new.additional_cost:g} {new.currency}.")
    for key, label in _DETAIL_LABELS.items():
        if old.flight_details.get(key) != new.flight_details.get(key):
            changes.append(f"{label} changed from {old.flight_details.get(key)} to {new.flight_details.get(key)}.")
    if old.eligibility != new.eligibility:
        changes.append(f"Eligibility changed from {old.eligibility} to {new.eligibility}.")
    return changes


class MockService:
    def __init__(self, scenarios: list[str] | None = None, today: date | None = None) -> None:
        self._names = scenarios if scenarios is not None else scenario_names()
        self._today = today
        self._lock = threading.RLock()
        self._bookings: dict[str, _Booking] = {}
        self.reset()

    def reset(self) -> None:
        """Reload every booking from its scenario file, discarding all simulated state."""
        with self._lock:
            loaded = [load_scenario(name, today=self._today) for name in self._names]
            self._bookings = {s.booking_id: _Booking(s) for s in loaded}

    def booking_ids(self) -> list[str]:
        return list(self._bookings)

    def _booking(self, booking_id: str) -> _Booking:
        if booking_id.startswith(DUFFEL_ID_PREFIXES):
            raise UnknownBookingError(f"'{booking_id}' looks like a Duffel id. The mock service never handles Duffel bookings.")
        try:
            return self._bookings[booking_id]
        except KeyError:
            raise UnknownBookingError(f"Mock booking '{booking_id}' not found") from None

    @staticmethod
    def _option(booking: _Booking, option_id: str) -> Option:
        try:
            return booking.options[option_id]
        except KeyError:
            raise UnknownOptionError(f"Option '{option_id}' not found for this booking") from None

    def get_trip_context(self, booking_id: str) -> TripContext:
        with self._lock:
            return self._booking(booking_id).scenario.trip.model_copy(deep=True)

    def get_option(self, booking_id: str, option_id: str) -> Option:
        """Read one option as it is now, without counting as shown to the traveler."""
        with self._lock:
            return self._option(self._booking(booking_id), option_id).model_copy(deep=True)

    def search_replacements(self, booking_id: str) -> list[Option]:
        """Every replacement option for the whole booking. Limits are applied by the harness, not here."""
        with self._lock:
            booking = self._booking(booking_id)
            for option_id, option in booking.options.items():
                booking.seen[option_id] = option.model_copy(deep=True)
            return [o.model_copy(deep=True) for o in booking.options.values()]

    def prepare_rebooking(self, booking_id: str, option_id: str) -> ValidationResult:
        """Recheck the option now. `changed` means it differs from what the traveler last saw."""
        with self._lock:
            booking = self._booking(booking_id)
            option = self._option(booking, option_id)
            latest = option.model_copy(deep=True)
            if booking.confirmation is not None:
                return ValidationResult(latest_option_details=latest, validation_result=provisional.RESULT_INVALID,
                                        changes_to_review=["This booking was already rebooked (simulated)."])
            result, reasons = _validate(option)
            if result != provisional.RESULT_VALID:
                booking.prepared = None
                return ValidationResult(latest_option_details=latest, validation_result=result, changes_to_review=reasons)
            seen = booking.seen.get(option_id)
            changes = _diff(seen, option) if seen is not None else []
            booking.seen[option_id] = latest.model_copy(deep=True)  # the traveler will now see this version
            if changes:
                booking.prepared = None  # a changed option needs a fresh review before it can be confirmed
                return ValidationResult(latest_option_details=latest, validation_result=provisional.RESULT_CHANGED,
                                        changes_to_review=changes)
            booking.prepared = (option_id, latest.model_copy(deep=True))
            return ValidationResult(latest_option_details=latest, validation_result=provisional.RESULT_VALID,
                                    changes_to_review=[])

    def complete_rebooking(self, booking_id: str, option_id: str) -> dict[str, Any]:
        """Complete the SIMULATED rebooking. Call only after the traveler explicitly confirmed this option."""
        with self._lock:
            booking = self._booking(booking_id)
            option = self._option(booking, option_id)
            if booking.confirmation is not None:
                raise AlreadyRebookedError(f"Booking '{booking_id}' was already rebooked (simulated)")
            result, reasons = _validate(option)
            if result != provisional.RESULT_VALID:
                raise RebookingNotAllowedError(" ".join(reasons))
            if booking.prepared is None or booking.prepared[0] != option_id:
                raise RebookingNotAllowedError("This option was not prepared and reviewed first.")
            if _diff(booking.prepared[1], option):
                raise RebookingNotAllowedError("This option changed after it was prepared and needs a new review.")
            booking.confirmation = {
                "confirmation_id": f"SIM-CONF-{booking_id}-{option_id}",
                "simulated": True,
                "data_source": "mock",
                "note": SIMULATED_NOTE,
                "booking_id": booking_id,
                "option_id": option_id,
                "additional_cost": option.additional_cost,
                "currency": option.currency,
                "updated_itinerary": dict(option.flight_details),
            }
            booking.prepared = None
            return dict(booking.confirmation)

    def get_confirmation(self, booking_id: str) -> dict[str, Any] | None:
        """The simulated confirmation if the booking was rebooked, else None."""
        with self._lock:
            confirmation = self._booking(booking_id).confirmation
            return dict(confirmation) if confirmation else None

    def escalate_to_support(self, booking_id: str, unresolved_issue: str, confirmed_needs: Limits) -> Handoff:
        """Prepare a SIMULATED handoff. `confirmed_needs` come from the harness; the mock invents none."""
        with self._lock:
            booking = self._booking(booking_id)
            trip = booking.scenario.trip
            handoff = Handoff(
                case_id=f"SIM-{booking_id}",
                booking_details={**trip.original_itinerary, "passenger_count": len(trip.passengers),
                                 "simulated": True, "label": HANDOFF_NOTE},
                confirmed_needs=confirmed_needs,
                unresolved_issue=unresolved_issue,
            )
            booking.handoffs.append(handoff)
            return handoff.model_copy(deep=True)
