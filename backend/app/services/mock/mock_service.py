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
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal

from ...contract.models import Handoff, Limits, Option, TripContext, ValidationResult
from ..airline_change import AirlineChange
from ..errors import (
    AlreadyRebookedError,
    RebookingNotAllowedError,
    ServiceError,
    UnknownBookingError,
    UnknownOptionError,
)
from ..validation import clock_text, diff_options, validate_option
from . import provisional
from .scenarios import Scenario, load_scenario, scenario_names

DUFFEL_ID_PREFIXES = ("ord_", "off_", "orq_", "oco_", "ocr_", "ocg_", "aic_", "sli_", "pas_")
SIMULATED_NOTE = "SIMULATED rebooking. No real airline ticket was created and nothing was sent to Duffel."
HANDOFF_NOTE = "SIMULATED support handoff. No real staff will follow up."


# Shared with the Duffel service; the mock names stay importable from here.
MockServiceError = ServiceError


class SimulatedFailureError(MockServiceError):
    """A fault switch made this call fail on purpose (see FAULTS)."""


# Switches that make the mock misbehave on purpose, for the harness's automated checks (PRD 3d). They change what
# the service reports, never the stored scenario data, so clearing them restores normal behavior.
FAULTS = (
    "unknown_eligibility",   # every option reports eligibility unknown
    "wrong_currency",        # every option reports EUR instead of USD
    "unavailable_option",    # the booking's first option reports unavailable
    "changed_details",       # after a search, options cost 15 more than the traveler was shown
    "tool_failure",          # search_replacements fails
    "uncertain_completion",  # the first complete_rebooking drops without a result and books nothing
)
CHANGED_DETAILS_EXTRA_COST = 15.0


class _Booking:
    def __init__(self, scenario: Scenario) -> None:
        self.scenario = scenario
        self.trip: TripContext = scenario.trip.model_copy(deep=True)  # changes below modify this copy only
        self.changes: list[AirlineChange] = []
        self.options: dict[str, Option] = {o.option_id: o.model_copy(deep=True) for o in scenario.options}
        self.seen: dict[str, Option] = {}  # option as last shown to the traveler (search or prepare)
        self.prepared: tuple[str, Option] | None = None  # (option_id, option as prepared)
        self.confirmation: dict[str, Any] | None = None
        self.handoffs: list[Handoff] = []
        self.faults: set[str] = set()
        self.faults_used: set[str] = set()  # once-only faults that already fired
        self.searched = False


_validate = validate_option
_diff = diff_options
_clock = clock_text


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

    def add_booking(self, scenario: Scenario) -> str:
        """Add a booking at runtime (for generated test bookings). reset() drops it again."""
        with self._lock:
            if scenario.booking_id in self._bookings:
                raise MockServiceError(f"Mock booking '{scenario.booking_id}' already exists")
            self._bookings[scenario.booking_id] = _Booking(scenario)
            return scenario.booking_id

    def set_faults(self, booking_id: str, faults: list[str]) -> list[str]:
        """Replace the active fault switches for a booking; an empty list clears them. Returns the active ones."""
        unknown = [f for f in faults if f not in FAULTS]
        if unknown:
            raise MockServiceError(f"Unknown faults {unknown}. Choose from: {', '.join(FAULTS)}")
        with self._lock:
            booking = self._booking(booking_id)
            booking.faults = set(faults)
            booking.faults_used.clear()
            booking.searched = False
            return sorted(booking.faults)

    def get_faults(self, booking_id: str) -> list[str]:
        with self._lock:
            return sorted(self._booking(booking_id).faults)

    @staticmethod
    def _current(booking: _Booking, option_id: str) -> Option:
        """The option as the service reports it right now, with any active faults applied (a copy)."""
        try:
            option = booking.options[option_id]
        except KeyError:
            raise UnknownOptionError(f"Option '{option_id}' not found for this booking") from None
        view = option.model_copy(deep=True)
        if "unknown_eligibility" in booking.faults:
            view.eligibility = provisional.UNKNOWN
        if "wrong_currency" in booking.faults:
            view.currency = "EUR"
        if "unavailable_option" in booking.faults and option_id == next(iter(booking.options)):
            view.validity = provisional.VALIDITY_UNAVAILABLE
        if "changed_details" in booking.faults and booking.searched:
            view.additional_cost = round(option.additional_cost + CHANGED_DETAILS_EXTRA_COST, 2)
        return view

    def _booking(self, booking_id: str) -> _Booking:
        if booking_id.startswith(DUFFEL_ID_PREFIXES):
            raise UnknownBookingError(f"'{booking_id}' looks like a Duffel id. The mock service never handles Duffel bookings.")
        try:
            return self._bookings[booking_id]
        except KeyError:
            raise UnknownBookingError(f"Mock booking '{booking_id}' not found") from None

    def get_trip_context(self, booking_id: str) -> TripContext:
        with self._lock:
            return self._booking(booking_id).trip.model_copy(deep=True)

    def add_airline_change(
        self, booking_id: str, kind: Literal["cancellation", "delay"], delay_minutes: int = 0
    ) -> AirlineChange:
        """Simulate an airline-initiated change: it updates the booking and is logged for the change check."""
        with self._lock:
            booking = self._booking(booking_id)
            if booking.confirmation is not None:
                raise AlreadyRebookedError(f"Booking '{booking_id}' was already rebooked (simulated)")
            itinerary = booking.trip.original_itinerary
            if kind == "delay":
                if delay_minutes <= 0:
                    raise ValueError("delay_minutes must be positive for a delay")
                moved = datetime.fromisoformat(itinerary["departs"]) + timedelta(minutes=delay_minutes)
                itinerary["departs"] = moved.isoformat(timespec="minutes")
                itinerary["status"] = "delayed"
                total = booking.trip.disruption_details.get("delay_minutes", 0) + delay_minutes
                booking.trip.disruption_details = {"type": "airline delay", "simulated": True, "delay_minutes": total}
                summary = f"The airline delayed the departure by {delay_minutes} minutes, to {_clock(moved)}."
            else:
                itinerary["status"] = "canceled"
                booking.trip.disruption_details = {"type": "airline cancellation", "simulated": True}
                summary = "The airline canceled this flight."
            change = AirlineChange(
                change_id=f"SIM-CHG-{booking_id}-{len(booking.changes) + 1}",
                booking_id=booking_id,
                kind=kind,
                summary=summary,
                detected_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                data_source="mock",
            )
            booking.changes.append(change)
            return change.model_copy(deep=True)

    def list_airline_changes(self, booking_id: str) -> list[AirlineChange]:
        """Every simulated change so far, oldest first. The caller tracks which ones it already showed."""
        with self._lock:
            return [c.model_copy(deep=True) for c in self._booking(booking_id).changes]

    def get_option(self, booking_id: str, option_id: str) -> Option:
        """Read one option as it is now, without counting as shown to the traveler."""
        with self._lock:
            return self._current(self._booking(booking_id), option_id)

    def search_replacements(self, booking_id: str) -> list[Option]:
        """Every replacement option for the whole booking. Limits are applied by the harness, not here."""
        with self._lock:
            booking = self._booking(booking_id)
            if "tool_failure" in booking.faults:
                raise SimulatedFailureError("Simulated tool failure: the replacement service is unavailable.")
            views = [self._current(booking, option_id) for option_id in booking.options]
            for view in views:
                booking.seen[view.option_id] = view.model_copy(deep=True)
            booking.searched = True  # faults like changed_details only act after the traveler has seen options
            return views

    def prepare_rebooking(self, booking_id: str, option_id: str) -> ValidationResult:
        """Recheck the option now. `changed` means it differs from what the traveler last saw."""
        with self._lock:
            booking = self._booking(booking_id)
            option = self._current(booking, option_id)
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
            option = self._current(booking, option_id)
            if booking.confirmation is not None:
                raise AlreadyRebookedError(f"Booking '{booking_id}' was already rebooked (simulated)")
            result, reasons = _validate(option)
            if result != provisional.RESULT_VALID:
                raise RebookingNotAllowedError(" ".join(reasons))
            if booking.prepared is None or booking.prepared[0] != option_id:
                raise RebookingNotAllowedError("This option was not prepared and reviewed first.")
            if _diff(booking.prepared[1], option):
                raise RebookingNotAllowedError("This option changed after it was prepared and needs a new review.")
            if "uncertain_completion" in booking.faults and "uncertain_completion" not in booking.faults_used:
                booking.faults_used.add("uncertain_completion")
                raise RuntimeError("Simulated connection drop: the result of the rebooking is unknown.")
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
